# Golden retrieval questions

Run locally against the real vault clone:

    python -m pytest tests/eval -m golden -v

Scored per question: correct note retrieved, leg correct, citation present.
Wrong-leg leak or a citation-less hit is a FAIL, not a warning.

1. Why did I stop using strategy X?
2. What are my strongest risk-management conclusions?
3. What lessons repeatedly appear after losses?
4. What indicators do I trust most?
5. What recurring themes exist across successful trades?
6. What mistakes do I repeatedly make?
7. What are my best trading insights about volatility?
8. How has my thinking on factor investing changed over time?
9. What did I believe before drawdown Y?
10. Find observations about earnings reactions.
