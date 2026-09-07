from pathlib import Path

# Canonical filesystem path for skill loading via SkillsProvider.from_paths().
SKILLS_PATH = Path(__file__).resolve().parent

__all__ = [
	"SKILLS_PATH",
]
