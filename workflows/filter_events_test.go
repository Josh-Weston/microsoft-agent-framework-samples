package main

import (
	"bytes"
	"encoding/json"
	"errors"
	"io"
	"os"
	"reflect"
	"strings"
	"testing"
	"time"
)

func TestReceiveTypedEvents(t *testing.T) {
	input := strings.Join([]string{
		`{"type":"started","data":null}`,
		`{"type":"superstep_started","iteration":2,"data":null}`,
		`{"type":"output","data":"hello"}`,
		`{"type":"output","data":{"type":"agent_response_update","contents":[]}}`,
		`{"type":"output","data":{"type":"agent_response_\u0075pdate"}}`,
		`{"type":"executor_completed","data":["done",{"type":"agent_response_update"}]}`,
		`{"type":"status","state":"IDLE"}`,
	}, "\n")
	var events []WorkflowEvent
	if err := receiveEvents(strings.NewReader(input), func(event WorkflowEvent) error {
		events = append(events, event)
		return nil
	}); err != nil {
		t.Fatal(err)
	}
	if len(events) != 5 {
		t.Fatalf("got %d events, want 5", len(events))
	}
	if events[0].Data != nil || events[0].Iteration != nil {
		t.Fatal("null values were not preserved")
	}
	if events[1].Iteration == nil || *events[1].Iteration != 2 {
		t.Fatal("iteration was not decoded")
	}
	if text, ok := events[2].Data.(TextData); !ok || text != "hello" {
		t.Fatalf("unexpected text data: %#v", events[2].Data)
	}
	list, ok := events[3].Data.(ListData)
	if !ok || len(list) != 1 {
		t.Fatalf("unexpected list: %#v", events[3].Data)
	}
	if list[0] != TextData("done") {
		t.Fatal("non-update list items must be retained")
	}
	if events[4].State == nil || *events[4].State != StateIdle {
		t.Fatal("state was not decoded")
	}
}

func TestFilterListUpdates(t *testing.T) {
	for _, test := range []struct {
		name string
		data string
		want string
	}{
		{"empty", `[]`, `[]`},
		{"only updates", `[{"type":"agent_response_update"}]`, `[]`},
		{"nulls and order", `[null,"first",{"type":"agent_response_update"},"last",null]`, `[null,"first","last",null]`},
		{"nested lists", `[[{"type":"agent_response_update"}],["text",null,{"type":"agent_response_update"}]]`, `[[],["text",null]]`},
	} {
		t.Run(test.name, func(t *testing.T) {
			var output bytes.Buffer
			if err := filterEvents(strings.NewReader(`{"type":"executor_completed","data":`+test.data+`}`), &output); err != nil {
				t.Fatal(err)
			}
			var event WorkflowEvent
			if err := json.Unmarshal(output.Bytes(), &event); err != nil {
				t.Fatal(err)
			}
			got, err := json.Marshal(event.Data)
			if err != nil {
				t.Fatal(err)
			}
			if string(got) != test.want {
				t.Fatalf("data = %s, want %s", got, test.want)
			}
		})
	}
}

func TestInvalidEvents(t *testing.T) {
	for _, input := range []string{
		"null", "[]", "{", "\n", "{} {}", "{}",
		`{"type":"output","data":true}`,
		`{"type":"output","data":{"type":"unknown"}}`,
		`{"type":"output","data":{"type":42}}`,
		`{"type":"output","data":{"agent_response":null}}`,
		`{"type":"superstep_started","iteration":"two"}`,
		`{"type":"output","data":{"type":"agent_response","created_at":"invalid"}}`,
	} {
		t.Run(input, func(t *testing.T) {
			err := filterEvents(strings.NewReader("{\"type\":\"started\"}\n"+input), io.Discard)
			if err == nil || !strings.Contains(err.Error(), "line 2:") {
				t.Fatalf("expected line 2 error, got %v", err)
			}
		})
	}
}

func TestLargeEvent(t *testing.T) {
	text := strings.Repeat("x", 2<<20)
	input := `{"type":"output","data":"` + text + `"}` + "\r\n"
	var output bytes.Buffer
	if err := filterEvents(strings.NewReader(input), &output); err != nil {
		t.Fatal(err)
	}
	var event WorkflowEvent
	if err := json.Unmarshal(output.Bytes(), &event); err != nil {
		t.Fatal(err)
	}
	if event.Data != TextData(text) {
		t.Fatal("large event text was changed")
	}
}

type failingWriter struct{}

func (failingWriter) Write([]byte) (int, error) {
	return 0, io.ErrClosedPipe
}

func TestOutputFailure(t *testing.T) {
	if err := filterEvents(strings.NewReader("{\"type\":\"started\"}\n"), failingWriter{}); !errors.Is(err, io.ErrClosedPipe) {
		t.Fatalf("expected write failure, got %v", err)
	}
}

func TestExport(t *testing.T) {
	input, err := os.ReadFile("events.jsonl")
	if err != nil {
		t.Fatal(err)
	}
	var output bytes.Buffer
	if err := filterEvents(bytes.NewReader(input), &output); err != nil {
		t.Fatal(err)
	}
	retained := bytes.Split(bytes.TrimSpace(output.Bytes()), []byte("\n"))
	if len(retained) != 36 {
		t.Fatalf("expected 36 retained events, got %d", len(retained))
	}
	index, updates, responses, nestedUpdates := 0, 0, 0, 0
	for _, line := range bytes.Split(bytes.TrimSpace(input), []byte("\n")) {
		// Compare independent generic representations to detect fields lost in the structs.
		var original map[string]json.RawMessage
		if err := json.Unmarshal(line, &original); err != nil {
			t.Fatal(err)
		}
		var header struct {
			Type string `json:"type"`
		}
		if err := json.Unmarshal(original["data"], &header); err == nil && header.Type == "agent_response_update" {
			updates++
			continue
		}
		var before, after any
		if err := json.Unmarshal(line, &before); err != nil {
			t.Fatal(err)
		}
		expected := before.(map[string]any)
		if items, ok := expected["data"].([]any); ok {
			kept := make([]any, 0, len(items))
			for _, item := range items {
				if object, ok := item.(map[string]any); ok && object["type"] == "agent_response_update" {
					nestedUpdates++
				} else {
					kept = append(kept, item)
				}
			}
			expected["data"] = kept
		}
		if index >= len(retained) {
			t.Fatal("missing retained event")
		}
		if err := json.Unmarshal(retained[index], &after); err != nil {
			t.Fatal(err)
		}
		normalizeTimestamps(before)
		normalizeTimestamps(after)
		if !reflect.DeepEqual(before, after) {
			t.Fatalf("event %d changed on typed round trip:\nbefore: %s\nafter: %s", index, line, retained[index])
		}
		var event WorkflowEvent
		if err := json.Unmarshal(retained[index], &event); err != nil {
			t.Fatal(err)
		}
		if response, ok := event.Data.(*AgentExecutorResponse); ok {
			responses++
			if response.AgentResponse.CreatedAt == nil ||
				response.AgentResponse.UsageDetails["total_token_count"] == 0 ||
				len(response.FullConversation) != 2 ||
				response.AgentResponse.Messages[0].Contents[0].Text == nil {
				t.Fatal("response metadata was not decoded")
			}
		}

		index++
	}
	if updates != 76 || index != 36 || responses != 2 {
		t.Fatalf("updates=%d retained=%d executor responses=%d", updates, index, responses)
	}
	if nestedUpdates == 0 {
		t.Fatal("export test did not exercise nested response-update removal")
	}
}

// time.Time preserves the instant, not redundant fractional zeros in JSON.
func normalizeTimestamps(value any) {
	switch value := value.(type) {
	case map[string]any:
		for key, item := range value {
			if text, ok := item.(string); ok && key == "created_at" {
				if timestamp, err := time.Parse(time.RFC3339Nano, text); err == nil {
					value[key] = timestamp.Format(time.RFC3339Nano)
				}
			} else {
				normalizeTimestamps(item)
			}
		}
	case []any:
		for _, item := range value {
			normalizeTimestamps(item)
		}
	}
}
