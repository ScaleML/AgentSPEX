"""ELAIPBench benchmark runner - main entry point.

Evaluates agents on academic paper question answering (403 questions).
Based on https://huggingface.co/datasets/KangKang625/ELAIPBench

Example usage:

# Run all questions with GPT-4.1
python src/benchmarks/elaipbench/run.py --model gpt-4.1

# Run 10 questions
python src/benchmarks/elaipbench/run.py --model claude-opus-4-6 --limit 10

# Run only single-answer questions
python src/benchmarks/elaipbench/run.py --model gpt-4.1 --question-type SA-MCQ

# Skip evaluation
python src/benchmarks/elaipbench/run.py --model gpt-4.1 --skip-eval
"""

import random
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import List

from benchmarks.elaipbench.config import ELAIPBenchResult, parse_args
from benchmarks.elaipbench.evaluate import evaluate
from benchmarks.elaipbench.instance import run_instance


def _load_questions(question_ids=None, question_type=None, limit=None) -> List[dict]:
    """Load questions from HuggingFace."""
    from datasets import load_dataset

    ds = load_dataset(
        "KangKang625/ELAIPBench", data_files="elabench.jsonl", split="train"
    )

    questions = []
    for idx, row in enumerate(ds):
        questions.append(
            {
                "id": idx,
                "paper_id": row["paper_id"],
                "question_type": row["question_type"],
                "question": row["question"],
                "answer": row["answer"],
                "relevant_passage": row["relevant_passage"],
                "paper_content": row["paper_content"],
            }
        )

    if question_type:
        questions = [q for q in questions if q["question_type"] == question_type]

    if question_ids:
        id_set = set(question_ids)
        questions = [q for q in questions if q["id"] in id_set]

    if limit and limit < len(questions):
        # questions = questions[:limit]
        questions = random.sample(questions, limit)

    return questions


def main():
    args = parse_args()

    # Step 1: Load questions from HuggingFace
    print("Loading ELAIPBench from HuggingFace...")
    questions = _load_questions(
        question_ids=args.question_ids,
        question_type=args.question_type,
        limit=args.limit,
    )
    print(f"\n{len(questions)} questions to process")

    # Step 2: Run agent on each question
    output_dir = Path(args.output_dir) / "runs"
    output_dir.mkdir(parents=True, exist_ok=True)

    results: List[ELAIPBenchResult] = []

    if args.max_parallel > 1:
        with ThreadPoolExecutor(max_workers=args.max_parallel) as executor:
            futures = {
                executor.submit(
                    run_instance, i + 1, len(questions), q, args, output_dir
                ): q
                for i, q in enumerate(questions)
            }
            for future in as_completed(futures):
                try:
                    results.append(future.result())
                except Exception as e:
                    q = futures[future]
                    results.append(
                        ELAIPBenchResult(
                            question_id=q["id"],
                            question=q["question"],
                            question_type=q["question_type"],
                            correct_answer=q["answer"],
                            status="failed",
                            error=str(e),
                        )
                    )
    else:
        for i, q in enumerate(questions):
            results.append(run_instance(i + 1, len(questions), q, args, output_dir))

    # Summary
    completed = [r for r in results if r.status == "completed"]
    correct = sum(1 for r in completed if r.is_correct)
    failed = len(results) - len(completed)

    print(f"\n{'='*60}")
    print(
        f"Completed: {len(completed)}/{len(results)}"
        + (f" ({failed} failed)" if failed else "")
    )
    if completed:
        print(f"Accuracy: {correct}/{len(completed)} ({correct/len(completed):.1%})")
    print(f"Results: {output_dir}")

    # Step 3: Evaluate
    if not args.skip_eval and completed:
        print("\nRunning evaluation...")
        eval_dir = Path(args.output_dir) / "evals"
        evaluate(runs_dir=str(output_dir), eval_dir=str(eval_dir))
    elif args.skip_eval:
        print("\nSkipped evaluation (--skip-eval)")

    print(f"{'='*60}")


if __name__ == "__main__":
    main()
