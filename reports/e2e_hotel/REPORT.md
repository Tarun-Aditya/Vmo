# End-to-end walkthrough: 25/25 features completed

Engine: Offline engine (Demo mode, no Claude). Corpus: 27 executed contracts, 5 drafts. Simulated systems: ERP, DocuSign, drives, mailbox, alert sinks.

✓ 1. Portfolio dashboard: decision queue, 30/60/90 buckets, Demo mode badge — 27 contracts and 5 drafts read from documents
✓ 2. Properties: cost per room with the share of group agreements, and what a buyer would inherit on a sale — 6 properties
✓ 3. Compare: one vendor across properties, rates and terms side by side, and what the gap is worth — about $60K a year at the best rate
✓ 4. Certificates: what each vendor must hold, read from the certificates on file, with expiry — 2 expired, 2 expiring, 4 not on file
✓ 5. Contracts repository with filters
✓ 6. Contract detail: fields with source, effective terms, hierarchy, signatures
✓ 7. Vendors and vendor profile with agreement tree
✓ 8. Key clauses matrix: every document by every clause, with citations
✓ 9. Admin adds a key clause; the next run finds it in every document — new column "Data residency" appeared in the matrix
✓ 10. Ask: a structured question (SQL, steps, table)
✓ 11. Ask: a clause question (semantic search, citations)
✓ 12. Review queue: drafts redlined against template and playbook
✓ 13. Upload a vendor draft: same pipeline, then tracked changes with findings — draft uploaded, deviations listed
✓ 14. Word-style editor: modes, presence, comment, suggestion
✓ 15. Share link: a guest opens the draft, comments, sees playbook findings
✓ 16. E-signature: DocuSign-compatible flow, signers sign in order, executed copy re-enters the pipeline — signed by both, now an executed contract
✓ 17. Pipeline: Run now, hash-based incremental run, per-file audit — new file read once, then skipped by hash on the next run
✓ 18. Connectors: simulated Coupa, SAP, Ariba, Drive, SharePoint and a mailbox, all through the real connector code
✓ 19. Spend vs contract, SLA and obligations derived from documents and feeds
✓ 20. Vendor risk scorecards and term benchmarks
✓ 21. Alerts: rules, notification centre, simulated Slack/Teams/webhook/e-mail
✓ 22. Templates: clause coverage and deviation heatmap; new contract from a template
✓ 23. Admin configuration: values, checklist, thresholds, risk weights, approvals, access, usage
✓ 24. Demo and Live: one switch changes the engine for every module
✓ 25. Security: two-factor setup

No page errors.