// Usage: go run workflows\filter_events.go [events.jsonl]
// Without a filename, reads JSONL from stdin. Decodes typed WorkflowEvents,
// skips top-level AgentResponseUpdates, removes updates from lists recursively,
// and marshals retained events to stdout. Empty lists remain lists.
package main

import (
	"bufio"
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"os"
	"time"
)

// Note: users can create their own events, so anything that doesn't match these
// predefined types will be treated as custom events and forwarded

type EventType string

const (
	// Workflow lifecycle events
	EventStarted      EventType = "started"
	EventStatus       EventType = "status"
	EventOutput       EventType = "output"
	EventIntermediate EventType = "intermediate"
	EventFailed       EventType = "failed"
	EventError        EventType = "error"
	EventWarning      EventType = "warning"

	// Executor events
	EventExecutorInvoked   EventType = "executor_invoked"
	EventExecutorCompleted EventType = "executor_completed"
	EventExecutorFailed    EventType = "executor_failed"

	// Superstep events
	EventSuperstepStarted   EventType = "superstep_started"
	EventSuperstepCompleted EventType = "superstep_completed"

	// Request events
	EventRequestInfo EventType = "request_info"
)

type EventSource string
type WorkflowRunState string

const (
	SourceFramework EventSource = "FRAMEWORK"
	SourceExecutor  EventSource = "EXECUTOR"
)

const (
	StateStarted                   WorkflowRunState = "STARTED"
	StateInProgress                WorkflowRunState = "IN_PROGRESS"
	StateInProgressPendingRequests WorkflowRunState = "IN_PROGRESS_PENDING_REQUESTS"
	StateIdle                      WorkflowRunState = "IDLE"
	StateIdleWithPendingRequests   WorkflowRunState = "IDLE_WITH_PENDING_REQUESTS"
	StateFailed                    WorkflowRunState = "FAILED"
	StateCancelled                 WorkflowRunState = "CANCELLED"
)

type WorkflowEvent struct {
	Type             EventType         `json:"type"`
	Data             EventData         `json:"data"`
	Origin           EventSource       `json:"origin"`
	State            *WorkflowRunState `json:"state"`
	Details          json.RawMessage   `json:"details"`
	ExecutorID       *string           `json:"executor_id"`
	RequestID        *string           `json:"_request_id"`
	SourceExecutorID *string           `json:"_source_executor_id"`
	RequestType      *string           `json:"_request_type"`
	ResponseType     *string           `json:"_response_type"`
	Iteration        *int              `json:"iteration"`
}

// EventData is a closed union of the payload shapes in this export.
// A nil interface represents JSON null.
type EventData interface {
	eventData()
}

type TextData string
type ListData []EventData

func (TextData) eventData() {}
func (ListData) eventData() {}

type AgentExecutorResponse struct {
	ExecutorID       string        `json:"executor_id"`
	AgentResponse    AgentResponse `json:"agent_response"`
	FullConversation []Message     `json:"full_conversation"`
}

func (*AgentExecutorResponse) eventData() {}

type AgentResponse struct {
	Type                 string                     `json:"type,omitempty"`
	Messages             []Message                  `json:"messages"`
	ResponseID           string                     `json:"response_id"`
	CreatedAt            *time.Time                 `json:"created_at,omitempty"`
	FinishReason         string                     `json:"finish_reason,omitempty"`
	UsageDetails         map[string]int64           `json:"usage_details,omitempty"`
	AdditionalProperties map[string]json.RawMessage `json:"additional_properties"`
}

func (*AgentResponse) eventData() {}

type AgentResponseUpdate struct {
	Type                 string                     `json:"type"`
	Contents             []Content                  `json:"contents"`
	Role                 string                     `json:"role,omitempty"`
	AuthorName           string                     `json:"author_name,omitempty"`
	ResponseID           string                     `json:"response_id,omitempty"`
	MessageID            string                     `json:"message_id,omitempty"`
	CreatedAt            *time.Time                 `json:"created_at,omitempty"`
	FinishReason         string                     `json:"finish_reason,omitempty"`
	ContinuationToken    *ContinuationToken         `json:"continuation_token,omitempty"`
	AdditionalProperties map[string]json.RawMessage `json:"additional_properties"`
	OperationState       string                     `json:"_operation_state,omitempty"`
}

func (*AgentResponseUpdate) eventData() {}

type ContinuationToken struct {
	ResponseID string `json:"response_id"`
}

type Message struct {
	Type                 string                     `json:"type"`
	Role                 string                     `json:"role"`
	Contents             []Content                  `json:"contents"`
	AuthorName           string                     `json:"author_name,omitempty"`
	MessageID            string                     `json:"message_id,omitempty"`
	AdditionalProperties map[string]json.RawMessage `json:"additional_properties"`
}

// Content models the text and usage entries present in the supplied export.
type Content struct {
	Type                 string                     `json:"type"`
	Text                 *string                    `json:"text,omitempty"`
	UsageDetails         map[string]int64           `json:"usage_details,omitempty"`
	MergeMode            string                     `json:"merge_mode,omitempty"`
	AdditionalProperties map[string]json.RawMessage `json:"additional_properties"`
}

func (event *WorkflowEvent) UnmarshalJSON(raw []byte) error {
	type plainEvent WorkflowEvent
	var decoded plainEvent
	wire := struct {
		*plainEvent
		Data json.RawMessage `json:"data"`
	}{plainEvent: &decoded}
	if err := json.Unmarshal(raw, &wire); err != nil {
		return err
	}
	if decoded.Type == "" {
		return fmt.Errorf("expected an event object with a nonempty type")
	}
	data, err := decodeEventData(wire.Data)
	if err != nil {
		return fmt.Errorf("data: %w", err)
	}
	decoded.Data = data
	*event = WorkflowEvent(decoded)
	return nil
}

func decodeEventData(raw json.RawMessage) (EventData, error) {
	raw = bytes.TrimSpace(raw)
	if len(raw) == 0 || bytes.Equal(raw, []byte("null")) {
		return nil, nil
	}
	switch raw[0] {
	case '"':
		var text TextData
		if err := json.Unmarshal(raw, &text); err != nil {
			return nil, err
		}
		return text, nil
	case '[':
		var items []json.RawMessage
		if err := json.Unmarshal(raw, &items); err != nil {
			return nil, err
		}
		list := make(ListData, len(items))
		for i, item := range items {
			value, err := decodeEventData(item)
			if err != nil {
				return nil, fmt.Errorf("item %d: %w", i, err)
			}
			list[i] = value
		}
		return list, nil
	case '{':
		var header struct {
			Type          string          `json:"type"`
			AgentResponse json.RawMessage `json:"agent_response"`
		}
		if err := json.Unmarshal(raw, &header); err != nil {
			return nil, err
		}
		var value EventData
		switch header.Type {
		case "agent_response_update":
			value = &AgentResponseUpdate{}
		case "agent_response":
			value = &AgentResponse{}
		case "":
			if len(header.AgentResponse) == 0 || bytes.Equal(bytes.TrimSpace(header.AgentResponse), []byte("null")) {
				return nil, fmt.Errorf("expected an agent_response in executor response")
			}
			value = &AgentExecutorResponse{}
		default:
			return nil, fmt.Errorf("unsupported payload type %q", header.Type)
		}
		if err := json.Unmarshal(raw, value); err != nil {
			return nil, err
		}
		return value, nil
	default:
		return nil, fmt.Errorf("expected null, text, a list, or an agent response object")
	}
}

func main() {
	if err := run(os.Args[1:], os.Stdin, os.Stdout); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}

func run(args []string, stdin io.Reader, stdout io.Writer) error {
	if len(args) > 1 {
		return fmt.Errorf("usage: go run workflows\\filter_events.go [events.jsonl]")
	}
	input := stdin
	if len(args) == 1 {
		file, err := os.Open(args[0])
		if err != nil {
			return err
		}
		defer file.Close()
		input = file
	}
	return filterEvents(input, stdout)
}

func filterEvents(input io.Reader, output io.Writer) error {
	encoder := json.NewEncoder(output)
	return receiveEvents(input, func(event WorkflowEvent) error {
		return encoder.Encode(event)
	})
}

// This will work, but needs to pull out the UsageDetails as well to match how the existing messages are stored
func removeResponseUpdates(data EventData) (EventData, bool) {
	switch value := data.(type) {
	case *AgentResponseUpdate:
		return nil, false
	case ListData:
		filtered := make(ListData, 0, len(value))
		for _, item := range value {
			if retained, keep := removeResponseUpdates(item); keep {
				filtered = append(filtered, retained)
			}
		}
		return filtered, true
	default:
		return data, true
	}
}

// receiveEvents delivers decoded events to application logic as they arrive.
func receiveEvents(input io.Reader, handle func(WorkflowEvent) error) error {
	reader := bufio.NewReader(input)
	for lineNumber := 1; ; lineNumber++ {
		line, err := reader.ReadBytes('\n')
		if err != nil && err != io.EOF {
			return fmt.Errorf("read line %d: %w", lineNumber, err)
		}
		if len(line) > 0 {
			var event WorkflowEvent
			if err := json.Unmarshal(line, &event); err != nil {
				return fmt.Errorf("line %d: %w", lineNumber, err)
			}
			if data, keep := removeResponseUpdates(event.Data); keep {
				event.Data = data
				if err := handle(event); err != nil {
					return fmt.Errorf("handle line %d: %w", lineNumber, err)
				}
			}

		}
		if err == io.EOF {
			return nil
		}
	}
}
