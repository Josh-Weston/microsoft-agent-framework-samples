"""Print the reverse of the text supplied on the command line."""

import argparse


def main() -> None:
	parser = argparse.ArgumentParser(description="Reverse text.")
	parser.add_argument("text", help="Text to reverse")
	args = parser.parse_args()
	print(args.text[::-1])


if __name__ == "__main__":
	main()
