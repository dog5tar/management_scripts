#!/usr/bin/env python3
"""
Process a CSV of YouTube videos (title,link) with yt-dlp, collecting:
- info JSON, description text
- subtitles/transcripts (authored + auto, converted to SRT)
- ALL comments (no cap)

Outputs a neat folder structure under ./out next to this script,
plus an AI-friendly Markdown packet (and optional PDF via Pandoc).

Usage:
  conda activate management_scripts
  python youtube_videos_for_episode_outline.py input.csv
"""

import argparse
import csv
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional

# ---------- Environment guard ----------

def check_conda_env(required_name: str = "management_scripts") -> None:
    current = os.environ.get("CONDA_DEFAULT_ENV") or ""
    if current == required_name:
        return
    prefix = os.environ.get("CONDA_PREFIX") or ""
    if prefix and Path(prefix).name == required_name:
        return
    msg = (
        f"[ERROR] This script must run inside the conda env '{required_name}'.\n"
        f"Current CONDA_DEFAULT_ENV='{current or 'N/A'}'.\n\n"
        f"Activate it and re-run:\n  conda activate {required_name}\n"
    )
    sys.exit(msg)

# ---------- Utilities ----------

def run(cmd: List[str], cwd: Optional[Path] = None) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

def which(name: str) -> Optional[str]:
    return shutil.which(name)

def ensure_dir(p: Path) -> Path:
    p.mkdir(parents=True, exist_ok=True)
    return p

def read_first_kb(path: Path, kb: int = 128) -> str:
    if not path.exists():
        return ""
    raw = path.read_bytes()[: kb * 1024]
    try:
        return raw.decode("utf-8", errors="ignore")
    except Exception:
        return raw.decode("latin-1", errors="ignore")

def quick_keywords(text: str, n: int = 30) -> List[str]:
    text = re.sub(r"[^\w\s\-]", " ", text, flags=re.UNICODE)
    tokens = [t.lower() for t in re.split(r"\s+", text) if len(t) >= 4]
    stop = {
        "http","https","www","youtube","channel","video","watch","with","this","that","from","have",
        "about","your","just","they","them","will","what","when","where","there","been","into",
        "because","really","also","some","more","like","does","dont","cant","wont","such","than",
        "then","ever","much","many","very","well","were","could","should","would"
    }
    freq: Dict[str,int] = {}
    for t in tokens:
        if t not in stop:
            freq[t] = freq.get(t, 0) + 1
    return [k for k,_ in sorted(freq.items(), key=lambda kv: kv[1], reverse=True)[:n]]

def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8", errors="ignore"))
    except Exception:
        return None

def flatten_comments(obj: Any) -> List[Dict[str, Any]]:
    """
    Flatten yt-dlp .comments.json into a list of {author, text, likes, replies}.
    We DO NOT trim the total set; this is only for light summary in the packet.
    """
    out: List[Dict[str, Any]] = []

    def visit(node):
        if isinstance(node, dict):
            if "text" in node:
                out.append({
                    "author": node.get("author") or node.get("author_id") or "unknown",
                    "text": re.sub(r"\s+", " ", str(node.get("text", ""))).strip(),
                    "likes": int(node.get("like_count") or node.get("likes") or 0),
                    "replies": int(node.get("reply_count") or 0),
                })
            for key in ("replies", "related_comments", "comments", "children"):
                if key in node and node[key]:
                    visit(node[key])
        elif isinstance(node, list):
            for x in node:
                visit(x)

    visit(obj)
    return out

# ---------- Core ----------

def probe_video_id(url: str) -> Optional[str]:
    """Use yt-dlp -J to get a stable ID without downloading media."""
    url = (url or "").strip()
    if not url:
        return None
    p = run(["yt-dlp", "-J", "--no-warnings", url])
    if p.returncode != 0:
        return None
    try:
        info = json.loads(p.stdout)
    except json.JSONDecodeError:
        return None
    return info.get("id")

def fetch_artifacts(url: str, vid: str, dest: Path, sub_langs: Optional[str]) -> Dict[str, Any]:
    """
    Use yt-dlp to fetch description, info JSON, subs (incl. auto), and ALL comments.
    No extractor-args: no caps or sorting — let yt-dlp pull everything it can.
    """
    ensure_dir(dest)
    outpat = str(dest / vid)

    args = [
        "yt-dlp",
        "--skip-download",
        "--write-info-json",
        "--write-description",
        "--write-sub", "--write-auto-sub",
        "--convert-subs", "srt",
        "--write-comments",
        "--no-warnings",
        "-o", outpat,
        url.strip()
    ]
    if sub_langs:
        # If you prefer everything, omit --sub-langs entirely (default grabs available).
        args[args.index("--write-sub")] = "--write-sub"  # keep flag
        args.insert(-1, "--sub-langs")
        args.insert(-1, sub_langs)

    p = run(args)
    if p.returncode != 0:
        sys.stderr.write(f"[yt-dlp] error for {url}:\n{p.stderr}\n")

    info = dest / f"{vid}.info.json"
    desc = dest / f"{vid}.description"
    comments = dest / f"{vid}.comments.json"
    subs = sorted(dest.glob(f"{vid}*.srt"))

    meta = load_json(info) or {}
    return {
        "id": vid,
        "url": url,
        "title": meta.get("title"),
        "channel": meta.get("channel"),
        "uploader": meta.get("uploader"),
        "upload_date": meta.get("upload_date"),
        "duration": meta.get("duration_string") or meta.get("duration"),
        "folder": str(dest),
        "info": str(info) if info.exists() else None,
        "desc": str(desc) if desc.exists() else None,
        "subs": [str(s) for s in subs],
        "comments": str(comments) if comments.exists() else None,
    }

def build_markdown(index: List[Dict[str, Any]], out_dir: Path) -> Path:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    md_path = out_dir / f"AI_Packet_{ts}.md"

    lines: List[str] = []
    lines.append("# AI Research Packet: YouTube Episodes")
    lines.append("")
    lines.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S %Z')}")
    lines.append("")
    lines.append("## Contents")
    for i, v in enumerate(index, 1):
        title = v.get("title") or v.get("id")
        channel = v.get("channel") or ""
        lines.append(f"{i}. [{title}](#video-{v['id']}) — {channel}")
    lines.append("")

    for v in index:
        lines.append("---")
        lines.append("")
        title = v.get("title") or v["id"]
        lines.append(f"## {title}  {{#video-{v['id']}}}")
        lines.append("")
        lines.append(f"**URL:** {v['url']}")
        lines.append(f"**Channel:** {v.get('channel','')}  |  **Uploader:** {v.get('uploader','')}  |  **Published:** {v.get('upload_date','')}  |  **Duration:** {v.get('duration','')}")
        lines.append(f"**Folder:** `{v['folder']}`")
        lines.append("")

        # Description (excerpt only; full file lives on disk)
        if v.get("desc"):
            desc = read_first_kb(Path(v["desc"]), kb=128).rstrip()
            if desc:
                lines.append("### Description (excerpt)")
                lines.append("")
                lines.append("```text")
                lines.append(desc)
                lines.append("```")
                lines.append("")

        # Transcript paths
        if v.get("subs"):
            lines.append("### Transcripts/Subtitles")
            for s in v["subs"]:
                lines.append(f"- `{s}`")
            lines.append("")

        # Surface keywords from desc+transcript (heuristic)
        seed = ""
        if v.get("desc"):
            seed += read_first_kb(Path(v["desc"]), kb=64)
        for s in v.get("subs", []):
            seed += "\n" + read_first_kb(Path(s), kb=64)
        kws = quick_keywords(seed, n=30)
        if kws:
            lines.append("### Surface Keywords (for cross-episode matching)")
            lines.append(", ".join(kws))
            lines.append("")

        # Comments: do not limit; in the packet we only summarize counts + file path to avoid huge PDFs
        if v.get("comments"):
            cj = load_json(Path(v["comments"]))
            count = 0
            if cj is not None:
                flat = flatten_comments(cj)
                count = len(flat)
            lines.append("### Comments")
            lines.append(f"- Total comments parsed (approx): **{count}**")
            lines.append(f"- Full comments JSON: `{v['comments']}`")
            lines.append("")

        # Files overview
        lines.append("### Files")
        if v.get("info"):   lines.append(f"- Info JSON: `{v['info']}`")
        if v.get("desc"):   lines.append(f"- Description: `{v['desc']}`")
        for s in v.get("subs", []):
            lines.append(f"- Transcript/Subtitle: `{s}`")
        if v.get("comments"): lines.append(f"- Comments JSON: `{v['comments']}`")
        lines.append("")

        # Planner stubs for your AI
        lines.append("### Episode Planner (for the AI)")
        lines.append("- **What viewers ask for (requests):**")
        lines.append("- **Common complaints/pain points:**")
        lines.append("- **New angles not covered in prior episodes:**")
        lines.append("- **Proposed outline:**")
        lines.append("")

    md_path.write_text("\n".join(lines), encoding="utf-8")
    return md_path

def maybe_pandoc(md_path: Path) -> Optional[Path]:
    pandoc = which("pandoc")
    if not pandoc:
        return None
    pdf_path = md_path.with_suffix(".pdf")
    cmd = [pandoc, str(md_path), "-o", str(pdf_path), "--from", "gfm"]
    p = run(cmd)
    if p.returncode == 0 and pdf_path.exists():
        return pdf_path
    return None

def main():
    # Enforce conda env
    check_conda_env("management_scripts")

    script_dir = Path(__file__).resolve().parent
    out_dir = ensure_dir(script_dir / "out")
    videos_root = ensure_dir(out_dir / "videos")

    ap = argparse.ArgumentParser(description="Build AI packet from a CSV of YouTube videos using yt-dlp (all comments, no caps).")
    ap.add_argument("csv", help="Input CSV with columns: title,link")
    ap.add_argument("--sub-langs", default=None, help='Subtitle language spec (e.g. "en.*,en"); omit to fetch all available')
    args = ap.parse_args()

    csv_path = Path(args.csv).resolve()
    if not csv_path.exists():
        sys.exit(f"CSV not found: {csv_path}")

    if which("yt-dlp") is None:
        sys.exit("yt-dlp not found on PATH. Install it first (e.g., `pipx install yt-dlp`).")

    # Read CSV (robust to stray spaces/BOM)
    rows: List[Dict[str,str]] = []
    with csv_path.open(newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for r in reader:
            url = (r.get("link") or r.get("Link") or r.get("url") or "").strip()
            title = (r.get("title") or r.get("Title") or "").strip()
            if url:
                rows.append({"title": title, "link": url})

    if not rows:
        sys.exit("CSV appears empty or lacks a 'link' column.")

    index: List[Dict[str, Any]] = []

    for r in rows:
        url = r["link"].strip()
        vid = probe_video_id(url)
        if not vid:
            print(f"[warn] Could not resolve ID for: {url}", file=sys.stderr)
            continue
        dest = ensure_dir(videos_root / vid)
        meta = fetch_artifacts(
            url=url,
            vid=vid,
            dest=dest,
            sub_langs=args.sub-langs if hasattr(args, "sub-langs") else args.sub_langs
            if hasattr(args, "sub_langs") else args.sub_langs,  # safeguard for odd shells
        )
        # prefer CSV title when present
        if r["title"] and not meta.get("title"):
            meta["title"] = r["title"]
        index.append(meta)

    if not index:
        sys.exit("No videos processed successfully.")

    md_path = build_markdown(index, out_dir)
    print(f"[ok] Markdown packet written: {md_path}")

    pdf = maybe_pandoc(md_path)
    if pdf:
        print(f"[ok] PDF written: {pdf}")
    else:
        print("[info] Pandoc not found or PDF conversion failed; keeping Markdown only.")

if __name__ == "__main__":
    main()

