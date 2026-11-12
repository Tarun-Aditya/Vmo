# End-to-end walkthrough: 22/22 features completed

Engine: Offline engine (Demo mode, no Claude). Corpus: 27 executed contracts, 5 drafts. Simulated systems: ERP, DocuSign, drives, mailbox, alert sinks.

✓ 1. Portfolio dashboard: decision queue, 30/60/90 buckets, Demo mode badge — 27 contracts and 5 drafts read from documents
✓ 2. Contracts repository with filters
✓ 3. Contract detail: fields with source, effective terms, hierarchy, signatures
✓ 4. Vendors and vendor profile with agreement tree
✓ 5. Key clauses matrix: every document by every clause, with citations
✓ 6. Admin adds a key clause; the next run finds it in every document — new column "Data residency" appeared in the matrix
✓ 7. Ask: a structured question (SQL, steps, table)
✓ 8. Ask: a clause question (semantic search, citations)
✓ 9. Review queue: drafts redlined against template and playbook
✓ 10. Upload a vendor draft: same pipeline, then tracked changes with findings — draft uploaded, deviations listed
✓ 11. Word-style editor: modes, presence, comment, suggestion
✓ 12. Share link: a guest opens the draft, comments, sees playbook findings
✓ 13. E-signature: DocuSign-compatible flow, signers sign in order, executed copy re-enters the pipeline — signed by both, now an executed contract
✓ 14. Pipeline: Run now, hash-based incremental run, per-file audit — new file read once, then skipped by hash on the next run
✓ 15. Connectors: simulated Coupa, SAP, Ariba, Drive, SharePoint and a mailbox, all through the real connector code
✓ 16. Spend vs contract, SLA and obligations derived from documents and feeds
✓ 17. Vendor risk scorecards and term benchmarks
✓ 18. Alerts: rules, notification centre, simulated Slack/Teams/webhook/e-mail
✓ 19. Templates: clause coverage and deviation heatmap; new contract from a template
✓ 20. Admin configuration: values, checklist, thresholds, risk weights, approvals, access, usage
✓ 21. Demo and Live: one switch changes the engine for every module
✓ 22. Security: two-factor setup

No page errors.