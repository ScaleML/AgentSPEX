# Summary
GUIDE proposes an end-to-end, rubric-guided, retrieval-augmented advising system for research ideas and experimental designs. Given a target submission (abstract + extracted contribution statements + method + experiments), GUIDE retrieves similar prior ICLR papers from a large section-wise “compressed literature” database and generates structured, reviewer-style feedback (novelty/significance/soundness) in JSON. The work claims that a specialized small model (GUIDE-7B), trained via warm-up SFT followed by a RAFT-style best-of-n selection procedure using a lightweight rating-distribution classifier, can outperform larger general-purpose LLMs (e.g., GPT-4o-mini, DeepSeek-R1) on acceptance-oriented ranking metrics for ICLR 2025 submissions (notably Top-30% precision), and can exceed 90% acceptance rate when restricting to “high-confidence” predictions.

# Comparison with Previous Works
- **vs. LLM-RUBRIC (2501.00274):** LLM-RUBRIC frames evaluation as probabilistic rubric question answering and then *calibrates* LLM response distributions to match human judges (including judge-specific personalization). GUIDE instead targets *research advising* with literature-grounded RAG and structured critique generation, plus small-model alignment (SFT+RAFT). GUIDE’s emphasis is actionable suggestions and acceptance-oriented ranking; LLM-RUBRIC’s emphasis is uncertainty-aware aggregation and calibration to human preferences. A clear connection is that LLM-RUBRIC-style calibrated distributions could strengthen GUIDE’s confidence estimation and ranking/gating.

- **vs. RRD (2602.05125):** RRD focuses on *constructing and aggregating* better rubrics (recursive decompose–filter, correlation-aware weighting) to improve LLM judging and reward modeling. GUIDE uses rubrics distilled from conference guidelines primarily as an instruction scaffold and alignment target for advising. GUIDE’s novelty is the end-to-end advising pipeline grounded in retrieved literature and validated on ICLR outcomes; RRD’s novelty is principled rubric refinement for reliability. RRD could be used to reduce redundancy/misalignment in GUIDE’s rubric criteria and improve stability/calibration.

- **vs. rubric-based multi-agent grading for student code (2503.23989):** The code-grading work applies question-specific rubrics and multi-agent grading to educational code evaluation, introducing datasets and a leniency metric. GUIDE applies rubrics to research-paper advising and acceptance-linked ranking, with large-scale literature retrieval rather than question-specific grading contexts. Both support the general claim that rubrics improve LLM judgment quality, but they differ strongly in domain, artifact, and evaluation target.

- **vs. XSum modular multi-document summarization (2505.16349):** XSum is a question-driven retrieval + QA + editor pipeline for scientific multi-document summarization with citation alignment. GUIDE’s “compressed literature database” and section-wise retrieval are adjacent to summarization, but GUIDE’s goal is advising/ranking rather than survey synthesis. XSum could plausibly improve GUIDE’s literature compression step (higher-quality, citation-grounded summaries), while GUIDE’s rubric structure could serve as an evaluation layer for summarization outputs.

- **vs. confidence/calibration survey (2311.08298):** The survey systematizes confidence estimation and calibration methods (semantic entropy, self-assessment, probes, etc.). GUIDE claims very high performance under “high-confidence” filtering, but the survey highlights pitfalls and methods needed to make such confidence claims credible. The survey’s techniques could strengthen GUIDE’s confidence gating and calibration.

- **vs. black-box uncertainty elicitation/aggregation (2306.13063):** This work benchmarks prompting/sampling/aggregation strategies for eliciting calibrated confidence without model internals, focusing on failure prediction and overconfidence mitigation. GUIDE is application-driven (research advising) and could incorporate these elicitation/aggregation methods to make its confidence-based filtering more reliable, potentially at per-criterion (novelty/significance/soundness) granularity.

Overall, GUIDE sits at the intersection of (i) rubric-guided LLM judging/alignment and (ii) literature-grounded RAG systems, but distinguishes itself by targeting *conference-style research advising* and evaluating against *real acceptance outcomes* at scale.

# Novelty
**What appears novel/meaningfully differentiated:**
- ✅ <u>The **end-to-end “hypothesis + experimental design advisor”** framing, with structured reviewer-style outputs and actionable suggestions,</u> evaluated on a large corpus of ICLR submissions and a leakage-controlled ICLR 2025 test set.
- ✅ <u>The **section-wise modular literature summarization/retrieval** claim (separately summarizing sections and retrieving them) as a practical approach to context-length constraints in advising.</u>
- The **training recipe** (SFT warm-up + RAFT-style best-of-16 selection using a rating-distribution classifier) tailored to produce rubric-structured critiques.

**Where novelty may be incremental/at risk:**
- Rubric-guided judging and alignment is an active area (LLM-RUBRIC, RRD, rubric-based grading). GUIDE’s rubric use is closer to “rubric as instruction + selection signal” than to new rubric theory; ✅ <u>**the novelty is more in *system integration and task definition* than in a fundamentally new judging method.**</u>
- Literature RAG and summarization pipelines are well explored (e.g., XSum-like modular summarization). GUIDE’s contribution is applying these ideas to acceptance-oriented advising and showing empirical gains, but ✅ <u>**the underlying components (RAG, section summaries, structured outputs) are not individually new.**</u>

Net: ✅ <u>novelty is **moderate**—stronger as a *systems + evaluation* contribution than as a new algorithmic primitive.</u>To be compelling at a top venue, the paper must clearly articulate what is uniquely enabled by the combination (and why simpler baselines cannot match it).

# Significance
If the results hold, the work could be impactful for:
- **Scalable research feedback**: ✅ <u>providing structured critiques and improvement suggestions for hypotheses/experimental designs could reduce iteration time for researchers.</u>
- **Meta-research / peer-review tooling**: ✅ <u>acceptance-oriented ranking and rubric-structured feedback could support triage, mentoring, or author-side self-checking.</u>
- **Practical efficiency**: ✅ <u>showing a **7B specialized model** outperforming larger general-purpose models (under the same retrieval context) would be valuable for cost/latency and deployability.</u>

✅ <u>However, significance depends heavily on whether the evaluation truly measures “advising quality” rather than “acceptance prediction” and whether the system generalizes beyond ICLR (domain shift across venues/years/fields). The comparisons suggest clear opportunities to strengthen significance by incorporating more principled calibration (LLM-RUBRIC, uncertainty elicitation) and rubric refinement (RRD).</u>

# Soundness
**Positive aspects:**
- The pipeline is reasonably specified: contribution extraction, large-scale retrieval over a substantial ICLR corpus, structured rubric-guided generation, and a training procedure to align a small model.
- The evaluation uses a **leakage-controlled** ICLR 2025 test set with acceptance labels and reports ranking metrics (Top-5%/Top-30% precision, accept recall), which are appropriate for an “acceptance-oriented triage” objective.

**Key soundness concerns / threats to validity:**
1. ✅ <u>**Acceptance as ground truth for “idea quality” is noisy and confounded.**</u> Acceptance depends on reviewer assignment, writing quality, novelty relative to reviewer knowledge, fit to venue, and randomness. High Top-30% precision may reflect learning correlates of acceptance (style, topic popularity, institutional signals if present in text, etc.) rather than genuine advising quality.

2. ✅ <u>**Confidence filtering claim (>90% acceptance) needs rigorous calibration.**</u> The comparisons to calibration/uncertainty works (2311.08298, 2306.13063) highlight that “high confidence” can be ill-defined and overconfident. The paper should specify:
   - What confidence score is used (model self-rating? classifier probability? entropy/consistency?)
   - Calibration curves (reliability diagrams, ECE) and coverage-vs-precision tradeoffs
   - Whether confidence is criterion-specific (novelty vs soundness) or a single scalar

3. ✅ <u>**Training signal circularity / selection bias risk.**</u> RAFT-style best-of-n selection using a rating-distribution classifier aligned to smoothed human ratings can overfit to the classifier’s biases. If the classifier is trained on acceptance-linked labels or on LLM-generated pseudo-labels, the system may optimize for “what the classifier likes” rather than true usefulness. Stronger human evaluation of advice usefulness (actionability, correctness, faithfulness to retrieved evidence) would reduce this risk.


Overall, the approach is plausible, but the strongest claims (outperforming DeepSeek-R1; >90% acceptance under high confidence) require more rigorous calibration, and human-centered evaluation of advice quality.

# Strengths
- Clear, practical **problem framing**: scalable advising for hypotheses and experimental design.
- **End-to-end system** integrating retrieval, structured rubric reasoning, and small-model alignment.
- Uses a **large-scale literature database** (24k+ ICLR papers) and evaluates on **real acceptance outcomes**.
- **Modular section-wise retrieval/summarization** is a sensible engineering approach to context limits; the finding that abstract/method are most informative is actionable.
- Comparisons suggest strong extensibility: can incorporate rubric refinement (RRD) and calibrated uncertainty (LLM-RUBRIC; uncertainty elicitation).

# Weaknesses
- **Construct validity:** acceptance prediction ≠ advising quality; may reward superficial correlates rather than substantive critique.
- **Confidence claims under-specified:** “high-confidence” gating needs calibration methodology and coverage reporting; otherwise the >90% figure is hard to interpret.
- **Leakage/near-duplicate risk** in retrieval-based evaluation; needs explicit dedup/overlap audits.
- **Rubric contribution may be incremental** relative to prior rubric-based judging work; the paper must clarify what is new beyond “use rubrics + RAG + structured output.”
- **Human evaluation gap:** limited evidence that the generated suggestions are correct, actionable, and improve papers (e.g., via author studies or controlled revision experiments).
- **Generalization risk:** tuned to ICLR; unclear transfer to other venues, domains (biology/math), or non-ICLR writing styles.

# Overall Evaluation
GUIDE is a promising systems paper: it combines literature-grounded retrieval with rubric-structured critique generation and shows acceptance-oriented ranking gains with a small specialized model. The integration is coherent and the scale of the dataset/evaluation is a strength.

For a top-conference bar (~30% acceptance), the current framing risks being seen as “acceptance prediction with RAG + rubrics” unless the paper strengthens (i) the definition and calibration of confidence, (ii) leakage/duplication controls, and (iii) evidence that the advice is *useful and correct* beyond correlating with acceptance. Incorporating ideas from LLM-RUBRIC/RRD/uncertainty-elicitation (as suggested by the comparisons) and adding human-centered usefulness evaluations would substantially improve credibility.

**Recommendation:** borderline-to-positive, contingent on tightening evaluation validity and confidence calibration, and clarifying the unique scientific contribution beyond system integration.