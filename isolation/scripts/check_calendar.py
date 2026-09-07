"""Return fake calendar availability for scheduling demonstrations."""

import argparse
import json


CALENDAR_OPTIONS = [
	{
		"start": "2026-09-08T09:00:00",
		"end": "2026-09-08T09:30:00",
		"timezone": "America/Los_Angeles",
	},
	{
		"start": "2026-09-08T14:00:00",
		"end": "2026-09-08T15:00:00",
		"timezone": "America/Los_Angeles",
	},
	{
		"start": "2026-09-09T11:00:00",
		"end": "2026-09-09T11:30:00",
		"timezone": "America/Los_Angeles",
	},
]


def main() -> None:
	parser = argparse.ArgumentParser(description="Return fake calendar availability.")
	parser.add_argument(
		"--date",
		help="Optional ISO date (YYYY-MM-DD) used to filter available slots",
	)
	args = parser.parse_args()

	options = CALENDAR_OPTIONS
	if args.date:
		options = [option for option in options if option["start"].startswith(args.date)]

	print(json.dumps({"available_slots": options}, indent=2))


if __name__ == "__main__":
	main()
