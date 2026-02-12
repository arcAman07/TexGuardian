"""Checkpoint and rollback management."""

from __future__ import annotations

import difflib
import hashlib
import json
import shutil
from datetime import datetime
from pathlib import Path


class CheckpointManager:
    """Manages file checkpoints for rollback."""

    def __init__(self, guardian_dir: Path):
        self.guardian_dir = guardian_dir
        self.checkpoints_dir = guardian_dir / "checkpoints"
        self.checkpoints_dir.mkdir(parents=True, exist_ok=True)
        self.index_file = self.checkpoints_dir / "index.json"
        self._index = self._load_index()

    async def create(
        self,
        description: str,
        files: list[Path],
    ) -> str:
        """Create a new checkpoint."""
        # Generate checkpoint ID
        timestamp = datetime.now()
        id_string = f"{timestamp.isoformat()}-{description}"
        checkpoint_id = hashlib.sha256(id_string.encode()).hexdigest()[:16]

        # Create checkpoint directory
        checkpoint_dir = self.checkpoints_dir / checkpoint_id
        checkpoint_dir.mkdir(exist_ok=True)

        # Copy files
        file_manifest = []
        for file_path in files:
            if file_path.exists():
                rel_path = file_path.name  # Filename only — sufficient since patches target one file
                dest = checkpoint_dir / rel_path
                shutil.copy2(file_path, dest)
                file_manifest.append({
                    "original": str(file_path),
                    "backup": str(dest),
                })

        # Save metadata
        metadata = {
            "id": checkpoint_id,
            "description": description,
            "timestamp": timestamp.isoformat(),
            "files": file_manifest,
        }
        (checkpoint_dir / "metadata.json").write_text(json.dumps(metadata, indent=2))

        # Update index
        self._index.insert(0, {
            "id": checkpoint_id,
            "description": description,
            "timestamp": timestamp.strftime("%Y-%m-%d %H:%M:%S"),
            "file_count": len(file_manifest),
        })
        self._save_index()

        return checkpoint_id

    async def restore(self, checkpoint_id: str) -> bool:
        """Restore files from a checkpoint."""
        checkpoint_dir = self.checkpoints_dir / checkpoint_id
        metadata_file = checkpoint_dir / "metadata.json"

        if not metadata_file.exists():
            return False

        metadata = json.loads(metadata_file.read_text())

        for file_info in metadata["files"]:
            backup_path = Path(file_info["backup"])
            original_path = Path(file_info["original"])

            if backup_path.exists():
                shutil.copy2(backup_path, original_path)

        return True

    async def diff(self, checkpoint_id: str) -> dict[str, str]:
        """Generate diff between checkpoint and current files."""
        checkpoint_dir = self.checkpoints_dir / checkpoint_id
        metadata_file = checkpoint_dir / "metadata.json"

        if not metadata_file.exists():
            return {}

        metadata = json.loads(metadata_file.read_text())
        diffs = {}

        for file_info in metadata["files"]:
            backup_path = Path(file_info["backup"])
            original_path = Path(file_info["original"])

            if backup_path.exists() and original_path.exists():
                old_content = backup_path.read_text(errors="ignore").splitlines()
                new_content = original_path.read_text(errors="ignore").splitlines()

                diff = difflib.unified_diff(
                    old_content,
                    new_content,
                    fromfile=f"a/{original_path.name}",
                    tofile=f"b/{original_path.name}",
                    lineterm="",
                )
                diff_text = "\n".join(diff)

                if diff_text:
                    diffs[str(original_path)] = diff_text

        return diffs

    def list_checkpoints(self) -> list[dict]:
        """List all checkpoints."""
        return self._index[:20]  # Return most recent 20

    def delete(self, checkpoint_id: str) -> bool:
        """Delete a checkpoint."""
        checkpoint_dir = self.checkpoints_dir / checkpoint_id

        if checkpoint_dir.exists():
            shutil.rmtree(checkpoint_dir)
            self._index = [c for c in self._index if c["id"] != checkpoint_id]
            self._save_index()
            return True

        return False

    def _load_index(self) -> list[dict]:
        """Load checkpoint index."""
        if self.index_file.exists():
            try:
                return json.loads(self.index_file.read_text())
            except json.JSONDecodeError:
                return []
        return []

    def _save_index(self) -> None:
        """Save checkpoint index."""
        self.index_file.write_text(json.dumps(self._index, indent=2))
