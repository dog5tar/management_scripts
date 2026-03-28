#!/usr/bin/env python3
"""
Batch-create BOTH speech and nonspeech labels for every WAV in a chosen directory.

What it does
------------
- Prompts for a directory of (already noise-gated) WAV files.
- Runs pyannote VAD -> writes <basename>_speech_labels.txt
- Inverts those -> writes <basename>_nonspeech_labels.txt
- Drops tiny speech blips and merges short gaps for cleaner labels.
- NEW: --min-nonspeech (default 3.0s) to ignore small pauses.
- Prints a per-file summary, including how many nonspeech segments were dropped.

Requirements
------------
- Run inside the specified conda env (see EXPECTED_ENV).
- Packages in that env: torch, torchaudio, pyannote.audio, huggingface_hub
- A valid HF token in --hf-token or $HF_TOKEN (accept model terms on HF).

Best practice
-------------
- Apply a NOISE GATE in Audacity first. Gating before VAD dramatically improves
  speech/nonspeech separation and reduces false "speech" detections from bleed.
"""

import os
import sys
import argparse
from pathlib import Path

# ---------- ENV GUARD: require a specific conda environment ----------
EXPECTED_ENV = "vad311"  # <-- change if your env is named differently
current_env = os.getenv("CONDA_DEFAULT_ENV")
if current_env != EXPECTED_ENV:
    sys.exit(
        f"[ERROR] This script must be run inside conda env '{EXPECTED_ENV}'.\n"
        f"Current env: '{current_env or 'None'}'\n"
        f"Activate with:  conda activate {EXPECTED_ENV}"
    )
# --------------------------------------------------------------------


# ---------- Duration helper ----------
def get_duration_torchaudio(wav_path: Path):
    try:
        import torchaudio
        info = torchaudio.info(str(wav_path))
        if info.sample_rate and info.num_frames and info.sample_rate > 0:
            return info.num_frames / info.sample_rate
    except Exception:
        pass
    return None
# --------------------------------------


# ---------- Label utilities ----------
def merge_overlaps(segs):
    """Merge overlapping or touching intervals."""
    if not segs:
        return []
    segs = sorted(segs, key=lambda x: x[0])
    merged = [list(segs[0])]
    for s, e in segs[1:]:
        ms, me = merged[-1]
        if s <= me + 1e-9:
            merged[-1][1] = max(me, e)
        else:
            merged.append([s, e])
    return [(s, e) for s, e in merged]


def expand(segs, pad, tmin=0.0, tmax=None):
    """Pad each interval on both sides (clamped to [tmin, tmax])."""
    out = []
    for s, e in segs:
        s2 = max(tmin, s - pad)
        e2 = e + pad
        if tmax is not None:
            e2 = min(tmax, e2)
        if e2 > s2:
            out.append((s2, e2))
    return out


def write_labels(segs, out_path: Path, tag="speech"):
    with out_path.open("w", encoding="utf-8") as f:
        for s, e in segs:
            f.write(f"{s:.6f}\t{e:.6f}\t{tag}\n")


def invert_intervals(speech, total_dur):
    """Return non-speech intervals covering [0, total_dur] \\ speech."""
    if not speech:
        return [(0.0, total_dur)]
    speech = merge_overlaps(speech)
    nonspeech, t = [], 0.0
    for s, e in speech:
        if s > t:
            nonspeech.append((t, s))
        t = max(t, e)
    if t < total_dur:
        nonspeech.append((t, total_dur))
    return [(s, e) for s, e in nonspeech if e - s > 1e-3]
# --------------------------------------


def load_pipeline(hf_token):
    from pyannote.audio import Pipeline
    if not hf_token:
        raise SystemExit("[ERROR] No Hugging Face token. Pass --hf-token or set HF_TOKEN.")
    try:
        return Pipeline.from_pretrained(
            "pyannote/voice-activity-detection",
            use_auth_token=hf_token
        )
    except Exception as e:
        raise SystemExit(
            "[ERROR] Could not load 'pyannote/voice-activity-detection'.\n"
            "1) Accept model terms: https://huggingface.co/pyannote/voice-activity-detection\n"
            "2) Verify your HF token (huggingface-cli whoami)\n"
            f"Details: {e}"
        )


def list_audio_files(base_dir: Path, recursive: bool = False):
    """Return all .wav/.wave files (case-insensitive)."""
    exts = {".wav", ".wave"}
    files = []
    if recursive:
        for p in base_dir.rglob("*"):
            if p.is_file() and p.suffix.lower() in exts:
                files.append(p)
    else:
        for p in base_dir.glob("*"):
            if p.is_file() and p.suffix.lower() in exts:
                files.append(p)
    return sorted(files)


def process_one_file(pipeline, wav_path: Path,
                     min_speech: float, min_gap: float,
                     pad: float, min_nonspeech: float):
    """Run VAD on wav_path and write speech/nonspeech labels. Return stats tuple."""

    # Duration (for inversion and padding clamp)
    total_dur = get_duration_torchaudio(wav_path)
    if total_dur is None:
        raise RuntimeError("Could not determine duration via torchaudio.")

    # Run VAD
    diar = pipeline(str(wav_path))

    # Collect raw speech segments
    speech = []
    for segment, _, label in diar.itertracks(yield_label=True):
        s, e = float(segment.start), float(segment.end)
        if e > s:
            speech.append((s, e))

    raw_speech_count = len(speech)

    # Merge overlaps, drop tiny speech segments
    speech = merge_overlaps(speech)
    speech = [(s, e) for s, e in speech if (e - s) >= min_speech]

    # Merge short gaps between speech segments
    merged = []
    for seg in sorted(speech, key=lambda x: x[0]):
        if not merged:
            merged.append(list(seg))
        else:
            ps, pe = merged[-1]
            if seg[0] - pe <= min_gap:
                merged[-1][1] = max(pe, seg[1])
            else:
                merged.append(list(seg))
    speech = [(s, e) for s, e in merged]
    cleaned_speech_count = len(speech)

    # File outputs
    out_dir = wav_path.parent
    base = wav_path.stem
    speech_file = out_dir / f"{base}_speech_labels.txt"
    nonspeech_file = out_dir / f"{base}_nonspeech_labels.txt"

    # Write speech labels
    write_labels(speech, speech_file, tag="speech")

    # Invert to nonspeech (pad speech edges to avoid clipping word boundaries)
    speech_expanded = expand(speech, pad=pad, tmin=0.0, tmax=total_dur)
    nonspeech_all = invert_intervals(speech_expanded, total_dur)

    # Filter out short nonspeech segments
    before_ns = len(nonspeech_all)
    nonspeech = [(s, e) for (s, e) in nonspeech_all if (e - s) >= min_nonspeech]
    dropped_ns = before_ns - len(nonspeech)

    # Write nonspeech labels
    write_labels(nonspeech, nonspeech_file, tag="nonspeech")

    return {
        "speech_labels_written": len(speech),
        "speech_labels_raw": raw_speech_count,
        "speech_labels_after_clean": cleaned_speech_count,
        "nonspeech_labels_written": len(nonspeech),
        "nonspeech_labels_before_filter": before_ns,
        "nonspeech_labels_dropped_short": dropped_ns,
        "speech_pad": pad,
        "min_speech": min_speech,
        "min_gap": min_gap,
        "min_nonspeech": min_nonspeech,
        "speech_file": speech_file.name,
        "nonspeech_file": nonspeech_file.name,
        "duration_sec": total_dur,
    }


def main():
    ap = argparse.ArgumentParser(
        description="Batch-create speech AND nonspeech labels for all WAVs in a directory."
    )
    ap.add_argument("--hf-token", default=None,
                    help="Hugging Face read token (or set HF_TOKEN in env)")
    ap.add_argument("--min-speech", type=float, default=0.30,
                    help="Drop speech segments shorter than this (s) [default 0.30]")
    ap.add_argument("--min-gap", type=float, default=0.25,
                    help="Merge speech gaps shorter than this (s) [default 0.25]")
    ap.add_argument("--pad", type=float, default=0.08,
                    help="Protect speech edges by padding (s) before invert [default 0.08]")
    ap.add_argument("--min-nonspeech", type=float, default=3.0,
                    help="Drop nonspeech segments shorter than this (s) [default 3.0]")
    args = ap.parse_args()

    # BIG reminder
    print("\n" + "=" * 80)
    print(" IMPORTANT: Apply a NOISE GATE in Audacity to the WAVs BEFORE using this script. ")
    print("=" * 80 + "\n")

    dir_in = input("Enter full path to the directory containing gated WAV files: ").strip()
    if not dir_in:
        sys.exit("[ERROR] No directory entered.")
    dir_path = Path(dir_in).expanduser()
    if not dir_path.exists() or not dir_path.is_dir():
        sys.exit(f"[ERROR] Not a directory: {dir_path}")

    recurse_ans = input("Search subfolders too? [y/N]: ").strip().lower()
    recursive = recurse_ans == "y"

    wavs = list_audio_files(dir_path, recursive=recursive)
    if not wavs:
        print("[ERROR] No WAV files found with extensions .wav or .wave.")
        print("If you're on macOS and pointing into Documents/Desktop, macOS may block")
        print("Python from reading there. Add your env's python to Full Disk Access, e.g.:")
        print(f"  {Path(sys.executable)}")
        # Debug sample
        sample = list(dir_path.rglob("*") if recursive else dir_path.glob("*"))
        print(f"[DEBUG] Sample of entries under {dir_path} (first 20):")
        for p in sample[:20]:
            print("  ", p)
        sys.exit(1)

    # Load VAD once
    hf_token = args.hf_token or os.getenv("HF_TOKEN")
    pipeline = load_pipeline(hf_token)

    print(f"[INFO] Found {len(wavs)} WAV file(s). Processing...\n")

    ok, failed = 0, 0
    for i, wav_path in enumerate(wavs, 1):
        print(f"[{i}/{len(wavs)}] {wav_path.name}")
        try:
            stats = process_one_file(
                pipeline, wav_path,
                min_speech=args.min_speech,
                min_gap=args.min_gap,
                pad=args.pad,
                min_nonspeech=args.min_nonspeech
            )

            # Per-file summary
            print(f"  ├─ Duration: {stats['duration_sec']:.2f}s")
            print(f"  ├─ Speech labels: raw={stats['speech_labels_raw']}, "
                  f"after_clean={stats['speech_labels_after_clean']} "
                  f"(min_speech={stats['min_speech']}s, min_gap={stats['min_gap']}s)")
            print(f"  ├─ Nonspeech labels: before_filter={stats['nonspeech_labels_before_filter']}, "
                  f"written={stats['nonspeech_labels_written']} "
                  f"(dropped_short={stats['nonspeech_labels_dropped_short']} "
                  f"@ min_nonspeech={stats['min_nonspeech']}s, pad={stats['speech_pad']}s)")
            print(f"  ├─ Wrote: {stats['speech_file']}")
            print(f"  └─ Wrote: {stats['nonspeech_file']}\n")
            ok += 1
        except Exception as e:
            print(f"  [ERROR] {e}\n")
            failed += 1

    print(f"[DONE] Success: {ok}, Failed: {failed}")
    print("\nNext steps in Audacity (per file):")
    print("  • Import *_nonspeech_labels.txt → Edit → Labeled Audio → Silence Audio (keeps timeline)")
    print("  • Or import *_speech_labels.txt → Edit → Labeled Audio → Cut (smart cut)")
    print("  • Master afterwards (Compression → Loudness Normalization → Limiter).")


if __name__ == "__main__":
    main()
