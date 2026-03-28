#!/usr/bin/env python3
"""
Batch-create BOTH speech and nonspeech labels for every WAV in a chosen directory.

Workflow:
  1) In Audacity, apply a NOISE GATE to each WAV in a folder (recommended).
  2) Run this script:  python speech_nonspeech_labels_batch.py
  3) When prompted, paste or type the path to the directory containing the gated WAVs.
  4) For each *.wav/*.WAV in that directory, the script writes:
       <basename>_speech_labels.txt
       <basename>_nonspeech_labels.txt
     in the same folder as the WAV.

Notes:
  - Requires: conda env (see EXPECTED_ENV), torch/torchaudio, pyannote.audio, huggingface_hub
  - Uses HF token from --hf-token or $HF_TOKEN
"""

import os, sys, argparse
from pathlib import Path

# ---------- ENV GUARD: require a specific conda environment ----------
EXPECTED_ENV = "vad311"  # <- change if your env has a different name
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
    if not segs: return []
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
    out = []
    for s, e in segs:
        s2 = max(tmin, s - pad)
        e2 = e + pad if tmax is None else min(tmax, e + pad)
        if e2 > s2:
            out.append((s2, e2))
    return out

def write_labels(segs, out_path: Path, tag="speech"):
    with out_path.open("w", encoding="utf-8") as f:
        for s, e in segs:
            f.write(f"{s:.6f}\t{e:.6f}\t{tag}\n")

def invert_intervals(speech, total_dur):
    """Return non-speech intervals covering [0, total_dur] \ speech."""
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
            "2) Verify (whoami) your HF token\n"
            f"Details: {e}"
        )

def process_one_file(pipeline, wav_path: Path, min_speech: float, min_gap: float, pad: float):
    # Duration (for inversion and padding clamp)
    total_dur = get_duration_torchaudio(wav_path)
    if total_dur is None:
        raise RuntimeError("Could not determine duration via torchaudio.")

    # Run VAD
    diar = pipeline(str(wav_path))

    # Collect speech segments
    speech = []
    for segment, _, label in diar.itertracks(yield_label=True):
        s, e = float(segment.start), float(segment.end)
        if e > s:
            speech.append((s, e))

    # Merge overlaps, drop tiny, merge tiny gaps
    speech = merge_overlaps(speech)
    speech = [(s, e) for s, e in speech if (e - s) >= min_speech]

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

    # File outputs
    out_dir = wav_path.parent
    base = wav_path.stem
    speech_file = out_dir / f"{base}_speech_labels.txt"
    nonspeech_file = out_dir / f"{base}_nonspeech_labels.txt"

    # Write speech labels
    write_labels(speech, speech_file, tag="speech")

    # Invert to nonspeech (pad speech edges to avoid clipping word boundaries)
    speech_expanded = expand(speech, pad=pad, tmin=0.0, tmax=total_dur)
    nonspeech = invert_intervals(speech_expanded, total_dur)
    write_labels(nonspeech, nonspeech_file, tag="nonspeech")

    return speech_file, nonspeech_file, len(speech), len(nonspeech)

def main():
    ap = argparse.ArgumentParser(
        description="Batch-create speech AND nonspeech labels for all WAVs in a directory."
    )
    ap.add_argument("--hf-token", default=None, help="Hugging Face read token (or set HF_TOKEN in env)")
    ap.add_argument("--min-speech", type=float, default=0.30,
                    help="Drop speech segments shorter than this (s) [default 0.30]")
    ap.add_argument("--min-gap", type=float, default=0.25,
                    help="Merge speech gaps shorter than this (s) [default 0.25]")
    ap.add_argument("--pad", type=float, default=0.08,
                    help="Protect speech edges by padding (s) before invert [default 0.08]")
    args = ap.parse_args()

    # BIG reminder
    print("\n" + "="*80)
    print(" IMPORTANT: Apply a NOISE GATE in Audacity to the WAVs BEFORE using this script. ")
    print("="*80 + "\n")

    dir_in = input("Enter full path to the directory containing gated WAV files: ").strip()
    if not dir_in:
        sys.exit("[ERROR] No directory entered.")
    dir_path = Path(dir_in).expanduser()
    if not dir_path.exists() or not dir_path.is_dir():
        sys.exit(f"[ERROR] Not a directory: {dir_path}")

    # Collect WAVs (non-recursive)
    wavs = sorted(list(dir_path.glob("*.wav")) + list(dir_path.glob("*.WAV")))
    if not wavs:
        sys.exit("[ERROR] No WAV files found in that directory.")

    # Load VAD once
    hf_token = args.hf_token or os.getenv("HF_TOKEN")
    pipeline = load_pipeline(hf_token)

    print(f"[INFO] Found {len(wavs)} WAV files. Processing...\n")

    ok, failed = 0, 0
    for i, wav_path in enumerate(wavs, 1):
        print(f"[{i}/{len(wavs)}] {wav_path.name}")
        try:
            speech_file, nonspeech_file, n_s, n_ns = process_one_file(
                pipeline, wav_path, args.min_speech, args.min_gap, args.pad
            )
            print(f"  ├─ Wrote: {speech_file.name}  (segments: {n_s})")
            print(f"  └─ Wrote: {nonspeech_file.name} (segments: {n_ns})\n")
            ok += 1
        except Exception as e:
            print(f"  [ERROR] {e}\n")
            failed += 1

    print(f"[DONE] Success: {ok}, Failed: {failed}")

    print("\nNext steps in Audacity (per file):")
    print("  • Import *_nonspeech_labels.txt → Edit → Labeled Audio → Silence Audio (keeps timeline)")
    print("  • Or import *_speech_labels.txt → Edit → Labeled Audio → Cut (smart cut)")
    print("  • Master afterwards (Loudness Normalization to -19 LUFS mono / -16 LUFS stereo, Peak -1.0 dB).")

if __name__ == "__main__":
    main()
