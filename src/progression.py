"""Versioned, atomic persistence for player progression."""

from __future__ import annotations

import json
import os
import shutil
from copy import deepcopy


SAVE_VERSION = 1


ACHIEVEMENTS = {
    "combo_master": {
        "name": "Air Combo",
        "desc": "Land a three-stomp combo before the timer resets.",
    },
    "all_characters": {
        "name": "Full Cast",
        "desc": "Complete any level with all four characters.",
    },
    "beige_final": {
        "name": "Classic Hero",
        "desc": "Defeat Sky Temple with Beige.",
    },
    "full_explorer": {
        "name": "Treasure Sweep",
        "desc": "Earn the exploration badge on every level.",
    },
    "lava_purity": {
        "name": "No First Aid",
        "desc": "Complete Lava Lake without collecting a heart.",
    },
    "hard_victory": {
        "name": "Hard-Fought Victory",
        "desc": "Complete the final level in Hard mode.",
    },
}


def default_progress() -> dict:
    return {
        "version": SAVE_VERSION,
        "high_score": 0,
        "unlocked_level": 0,
        "levels": {},
        "achievements": {},
        "settings": {
            "muted": False,
            "tutorial_hints": True,
            "screen_shake": True,
            "difficulty": "normal",
        },
    }


class ProgressionStore:
    def __init__(self, path: str, level_count: int):
        self.path = path
        self.level_count = max(1, level_count)
        self.data = self.load()

    def load(self) -> dict:
        try:
            with open(self.path, "r", encoding="utf-8") as handle:
                raw = json.load(handle)
            return self._normalise(raw)
        except FileNotFoundError:
            return default_progress()
        except (OSError, ValueError, TypeError):
            self._backup_corrupt_file()
            return default_progress()

    def _normalise(self, raw) -> dict:
        if not isinstance(raw, dict):
            raise TypeError("save root must be an object")
        data = default_progress()
        data["high_score"] = max(0, int(raw.get("high_score", 0)))
        unlocked = int(raw.get("unlocked_level", 0))
        data["unlocked_level"] = max(0, min(unlocked, self.level_count - 1))
        levels = raw.get("levels", {})
        if isinstance(levels, dict):
            for key, value in levels.items():
                if isinstance(value, dict):
                    data["levels"][str(key)] = deepcopy(value)
        settings = raw.get("settings", {})
        if isinstance(settings, dict):
            for key in ("muted", "tutorial_hints", "screen_shake"):
                if key in settings:
                    data["settings"][key] = bool(settings[key])
            difficulty = str(settings.get("difficulty", "normal")).lower()
            if difficulty in ("easy", "normal", "hard"):
                data["settings"]["difficulty"] = difficulty
        achievements = raw.get("achievements", {})
        if isinstance(achievements, dict):
            for ach_id, value in achievements.items():
                if ach_id in ACHIEVEMENTS:
                    if isinstance(value, dict):
                        unlocked = bool(value.get("unlocked", False))
                        unlocked_at = value.get("unlocked_at")
                    else:
                        unlocked = bool(value)
                        unlocked_at = None
                    if unlocked:
                        record = {
                            "unlocked": True,
                            "name": ACHIEVEMENTS[ach_id]["name"],
                            "desc": ACHIEVEMENTS[ach_id]["desc"],
                        }
                        if unlocked_at is not None:
                            record["unlocked_at"] = unlocked_at
                        data["achievements"][ach_id] = record
        return data

    def _backup_corrupt_file(self):
        if not os.path.exists(self.path):
            return
        backup = f"{self.path}.corrupt"
        try:
            shutil.copy2(self.path, backup)
        except OSError:
            pass

    def save(self):
        directory = os.path.dirname(self.path) or "."
        os.makedirs(directory, exist_ok=True)
        temp_path = f"{self.path}.tmp"
        try:
            with open(temp_path, "w", encoding="utf-8") as handle:
                json.dump(self.data, handle, indent=2, sort_keys=True)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_path, self.path)
        finally:
            try:
                if os.path.exists(temp_path):
                    os.remove(temp_path)
            except OSError:
                pass

    def level_record(self, level_index: int) -> dict:
        return self.data["levels"].get(str(level_index), {})

    def unlock_achievement(self, achievement_id: str) -> dict | None:
        """Persist an achievement and return its display record if it is new."""
        if achievement_id not in ACHIEVEMENTS:
            raise KeyError(f"unknown achievement: {achievement_id}")
        achievements = self.data.setdefault("achievements", {})
        if achievements.get(achievement_id, {}).get("unlocked"):
            return None
        definition = ACHIEVEMENTS[achievement_id]
        record = {
            "unlocked": True,
            "name": definition["name"],
            "desc": definition["desc"],
        }
        achievements[achievement_id] = record
        self.save()
        return {"id": achievement_id, **record}

    def record_level(self, level_index: int, result: dict):
        key = str(level_index)
        previous = self.data["levels"].get(key, {})
        best_time = previous.get("best_time")
        current_time = float(result["time"])
        characters = set(previous.get("characters", []))
        characters.add(str(result["character"]))
        old_badges = previous.get("badges", {})
        if not old_badges:
            old_stars = int(previous.get("stars", 0))
            old_badges = {
                "complete": old_stars >= 1,
                "exploration": old_stars >= 2,
                "skill": old_stars >= 3,
            }
        new_badges = result.get("badges", {})
        badges = {
            name: bool(old_badges.get(name, False) or new_badges.get(name, False))
            for name in ("complete", "exploration", "skill")
        }
        self.data["levels"][key] = {
            "name": str(result["name"]),
            "best_score": max(int(previous.get("best_score", 0)), int(result["score"])),
            "best_time": current_time if best_time is None else min(float(best_time), current_time),
            "best_collection": max(
                float(previous.get("best_collection", 0.0)),
                float(result["collection_ratio"]),
            ),
            "badges": badges,
            "stars": sum(badges.values()),
            "characters": sorted(characters),
            "best_difficulty": str(result.get("difficulty", "normal")),
        }
        self.data["high_score"] = max(
            int(self.data.get("high_score", 0)), int(result["total_score"])
        )
        self.data["unlocked_level"] = min(
            self.level_count - 1,
            max(int(self.data.get("unlocked_level", 0)), level_index + 1),
        )
        self.save()
