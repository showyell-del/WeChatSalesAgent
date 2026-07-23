# Phase 2 Summary

Implemented the deterministic private-chat corpus and immutable evidence index.

The full 183-day run inspected every session in the published account generation. It produced 244 eligible bidirectional private conversations, excluded 958 group/official/system/one-way sessions with explicit reason codes, and published 47,479 evidence references. Rebuilding a corpus reuses stable evidence IDs through a separate mapping table instead of duplicating evidence bodies.

Deterministic inbound-only extraction produced 739 fact references. Sampling exposed overly broad time, region, WeChat-ID, and generic-course rules; those paths were removed and replaced with constrained business-relevant patterns before the final full rebuild.
