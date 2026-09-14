# =============================================================================
# evaluate_verification.py
# =============================================================================
# Standalone accuracy evaluation for the exam_verification pipeline (OCR name/
# roll matching, document-type detection, expiry checking, DeepFace face
# matching). Not part of the Streamlit app — run it directly from the
# command line against a manifest of test image pairs to produce the numbers
# for a Results/Evaluation section (e.g. Table II of the IEEE writeup).
#
# It calls the same pure functions verify_student_identity() uses
# (_extract_id_card_text, detect_document_type, check_id_card_text,
# check_expiry, check_face_match) directly, so the measured accuracy is the
# accuracy of the exact code path students go through — no Streamlit runtime
# or database connection is needed to run this script.
#
# Usage:
#   python evaluate_verification.py --manifest manifest.csv --out results.csv
#   python evaluate_verification.py --manifest manifest.csv --out results.csv --sweep
#
# See MANIFEST FORMAT below for the expected CSV columns.
# =============================================================================

import argparse
import csv
import sys
from pathlib import Path

from PIL import Image

# Allow running this file directly (python evaluate_verification.py) without
# installing the app as a package — add the repo root to sys.path so
# `from exam_verification_feature import ...` and `from db import ...`
# (imported transitively) resolve the same way they do inside the Streamlit app.
_REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_REPO_ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from exam_verification_feature import (  # noqa: E402
    _extract_id_card_text,
    detect_document_type,
    check_id_card_text,
    check_expiry,
    check_face_match,
    _EXPIRING_DOCUMENT_TYPES,
)

# =============================================================================
# MANIFEST FORMAT
# =============================================================================
# A CSV with one row per test attempt (one ID-card / selfie pair). Columns:
#
#   pair_id             free-text identifier, e.g. "S01_genuine_1"
#   id_card_image       path to the ID card photo (relative to the manifest
#                        file's own directory, or absolute)
#   selfie_image        path to the selfie photo
#   first_name          the name printed on THIS id_card_image (i.e. the
#                        card owner's first name)
#   last_name           the card owner's last name
#   roll_no             the card owner's student/roll number, or blank
#   pair_type           "genuine" if selfie_image is a photo of the SAME
#                        person as id_card_image, "impostor" if it is a
#                        DIFFERENT person's selfie paired with this card
#                        (used to measure face-match FAR/FRR)
#   doc_type_truth      optional ground-truth document type: one of
#                        student_card, bc_drivers_licence,
#                        bc_services_card_or_bcid, other_gov_id — leave
#                        blank to skip document-type-accuracy scoring for
#                        this row
#   expired_truth        optional ground truth for the expiry check: "true",
#                        "false", or blank if not applicable/unknown
#
# Note: name_ok/roll_ok/doc-type accuracy are evaluated against the ID
# CARD's actual owner regardless of pair_type, because OCR only reads the
# card — swapping in a different person's selfie (an impostor row) does not
# change what is printed on the card. Only the face-match outcome depends on
# pair_type.
# =============================================================================


def _load_manifest(manifest_path: Path):
    base_dir = manifest_path.parent
    rows = []
    with open(manifest_path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            row["_id_card_path"] = _resolve(base_dir, row["id_card_image"])
            row["_selfie_path"] = _resolve(base_dir, row["selfie_image"])
            rows.append(row)
    return rows


def _resolve(base_dir: Path, raw_path: str) -> Path:
    p = Path(raw_path)
    return p if p.is_absolute() else (base_dir / p)


def _parse_bool(value: str):
    v = (value or "").strip().lower()
    if v in ("true", "1", "yes"):
        return True
    if v in ("false", "0", "no"):
        return False
    return None


def _run_one(row: dict) -> dict:
    id_card_image = Image.open(row["_id_card_path"])
    selfie_image = Image.open(row["_selfie_path"])

    ocr_text = _extract_id_card_text(id_card_image)
    doc_type = detect_document_type(ocr_text)
    text_result = check_id_card_text(
        ocr_text, row.get("first_name", ""), row.get("last_name", ""), row.get("roll_no", "")
    )
    expiry_result = (
        check_expiry(ocr_text) if doc_type in _EXPIRING_DOCUMENT_TYPES else {"expiry_date": None, "expired": None}
    )
    face_result = check_face_match(id_card_image, selfie_image)

    roll_check_applies = doc_type == "student_card" and bool(row.get("roll_no"))
    roll_required_ok = text_result["roll_ok"] if roll_check_applies else True
    expiry_ok = not expiry_result["expired"]
    passed = (
        text_result["name_ok"]
        and roll_required_ok
        and expiry_ok
        and face_result.get("verified", False)
    )

    return {
        "pair_id": row.get("pair_id", ""),
        "pair_type": row.get("pair_type", ""),
        "doc_type_detected": doc_type,
        "doc_type_truth": row.get("doc_type_truth", ""),
        "name_ok": text_result["name_ok"],
        "roll_ok": text_result["roll_ok"] if roll_check_applies else "",
        "expired_detected": expiry_result["expired"],
        "expired_truth": row.get("expired_truth", ""),
        "expiry_date_detected": expiry_result.get("expiry_date", ""),
        "face_verified": face_result.get("verified", False),
        "face_distance": face_result.get("distance", ""),
        "face_threshold": face_result.get("threshold", ""),
        "face_error": face_result.get("error", ""),
        "passed": passed,
        # Raw OCR text — kept last so it doesn't crowd the earlier columns
        # when viewed in a spreadsheet; invaluable for diagnosing exactly
        # what EasyOCR actually read off a card vs. what's printed on it.
        "ocr_text": ocr_text,
    }


def _pct(numerator: int, denominator: int) -> str:
    if denominator == 0:
        return "n/a"
    return f"{100.0 * numerator / denominator:.1f}%  ({numerator}/{denominator})"


def _print_summary(results: list[dict]):
    genuine = [r for r in results if r["pair_type"] == "genuine"]
    impostor = [r for r in results if r["pair_type"] == "impostor"]
    doc_type_scored = [r for r in results if r["doc_type_truth"]]
    expiry_scored = [r for r in results if r["expired_truth"] != ""]

    print("\n================ VERIFICATION EVALUATION SUMMARY ================\n")

    print(f"Total pairs evaluated:      {len(results)}")
    print(f"  genuine pairs:            {len(genuine)}")
    print(f"  impostor pairs:           {len(impostor)}\n")

    name_ok_count = sum(1 for r in results if r["name_ok"])
    print(f"OCR name-match rate (all rows):        {_pct(name_ok_count, len(results))}")

    if doc_type_scored:
        correct = sum(1 for r in doc_type_scored if r["doc_type_detected"] == r["doc_type_truth"])
        print(f"Document-type detection accuracy:      {_pct(correct, len(doc_type_scored))}")

    if expiry_scored:
        correct = sum(1 for r in expiry_scored if r["expired_detected"] == _parse_bool(r["expired_truth"]))
        print(f"Expiry-check accuracy:                 {_pct(correct, len(expiry_scored))}")

    if genuine:
        tar = sum(1 for r in genuine if r["face_verified"])
        print(f"Face-match TAR (true accept, genuine): {_pct(tar, len(genuine))}")
        print(f"Face-match FRR (false reject, genuine): {_pct(len(genuine) - tar, len(genuine))}")

    if impostor:
        far = sum(1 for r in impostor if r["face_verified"])
        print(f"Face-match FAR (false accept, impostor): {_pct(far, len(impostor))}")

    if genuine:
        end_to_end_correct = sum(1 for r in genuine if r["passed"])
        print(f"End-to-end accuracy on genuine pairs:  {_pct(end_to_end_correct, len(genuine))}")
    if impostor:
        end_to_end_correct = sum(1 for r in impostor if not r["passed"])
        print(f"End-to-end correct-rejection on impostors: {_pct(end_to_end_correct, len(impostor))}")

    print("\n====================================================================\n")


def _sweep_thresholds(results: list[dict], steps=9):
    """
    Recompute face-match FAR/FRR at several thresholds by scaling the
    model's own decision threshold (DeepFace returns 'threshold' alongside
    'distance' — decision was verified iff distance <= threshold). Only
    rows with a numeric distance/threshold (i.e. no face_error) count.
    """
    scored = [r for r in results if r["face_distance"] != "" and r["face_threshold"] != ""]
    genuine = [r for r in scored if r["pair_type"] == "genuine"]
    impostor = [r for r in scored if r["pair_type"] == "impostor"]
    if not scored:
        print("No rows with usable face distances to sweep (all rows had face_error).")
        return

    base_threshold = float(scored[0]["face_threshold"])
    print("\n---------------- Threshold sweep (scaling the model's default threshold) ----------------")
    print(f"{'scale':>6}  {'threshold':>10}  {'FRR (genuine)':>15}  {'FAR (impostor)':>15}")
    for i in range(steps):
        scale = 0.6 + i * (0.8 / max(steps - 1, 1))  # sweep 0.6x .. 1.4x of base
        t = base_threshold * scale
        frr = _pct(
            sum(1 for r in genuine if float(r["face_distance"]) > t), len(genuine)
        ) if genuine else "n/a"
        far = _pct(
            sum(1 for r in impostor if float(r["face_distance"]) <= t), len(impostor)
        ) if impostor else "n/a"
        print(f"{scale:6.2f}  {t:10.4f}  {frr:>15}  {far:>15}")
    print("-------------------------------------------------------------------------------------------\n")


def main():
    parser = argparse.ArgumentParser(description="Evaluate the exam_verification OCR/face-match pipeline.")
    parser.add_argument("--manifest", required=True, type=Path, help="Path to the manifest CSV.")
    parser.add_argument("--out", type=Path, default=None, help="Optional path to write per-row results CSV.")
    parser.add_argument(
        "--sweep", action="store_true", help="Also print a face-match threshold sweep (FAR/FRR trade-off)."
    )
    args = parser.parse_args()

    rows = _load_manifest(args.manifest)
    if not rows:
        print("Manifest is empty.")
        return

    results = []
    for i, row in enumerate(rows, start=1):
        print(f"[{i}/{len(rows)}] {row.get('pair_id', '?')} ...", flush=True)
        try:
            results.append(_run_one(row))
        except Exception as exc:  # keep going even if one pair errors out
            print(f"  FAILED: {exc}")
            results.append(
                {
                    "pair_id": row.get("pair_id", ""),
                    "pair_type": row.get("pair_type", ""),
                    "doc_type_detected": "ERROR",
                    "doc_type_truth": row.get("doc_type_truth", ""),
                    "name_ok": False,
                    "roll_ok": "",
                    "expired_detected": "",
                    "expired_truth": row.get("expired_truth", ""),
                    "expiry_date_detected": "",
                    "face_verified": False,
                    "face_distance": "",
                    "face_threshold": "",
                    "face_error": str(exc),
                    "passed": False,
                    "ocr_text": "",
                }
            )

    if args.out:
        with open(args.out, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=list(results[0].keys()))
            writer.writeheader()
            writer.writerows(results)
        print(f"\nPer-row results written to {args.out}")

    _print_summary(results)
    if args.sweep:
        _sweep_thresholds(results)


if __name__ == "__main__":
    main()
