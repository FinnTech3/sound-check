# Agensi checklist

Every skill in these repos must pass this list before it is uploaded. `python3 tools/agensi_build.py` enforces the
rules marked **[auto]**. The rest need a person or an agent run.

Sources: agensi.io/docs (packaging, review-and-approval, submit-on-the-website, how-agents-load-skills,
protect-your-work, pricing-your-skill) and the creator guides on agensi.io/learn.

## 1. How Agensi delivers a skill (design around this)

- [ ] Delivery is MCP only. Agents get text files and are told never to save them. Nothing is installed on the
      buyer's machine: no plugins, hooks, slash commands or MCP server settings. **[auto: scans, not designs]**
- [ ] Scripts run from a temporary file, unchanged, and are deleted afterwards. A script cannot read other files in
      the package, so each script is self-contained and takes paths as arguments. **[auto]** `SKILL.md` must tell the
      agent to write the script to a temporary file, and must not run `python3 scripts/...` by path.
- [ ] Only text reaches the buyer: no images, PDFs or binaries inside the zip. **[auto]**
- [ ] If the skill needs outside software (for example a CLI), say so on a `Requires:` line near the top of
      `SKILL.md`, and never install it without the user's go-ahead. **[auto for scripts]**
- [ ] Logic in each script stays under about 20 KB, split if larger. **[auto]**

## 2. Package (the zip)

- [ ] One top folder, `SKILL.md` at its root (or 2 to 50 `SKILL.md` files for a pack). **[auto]**
- [ ] Under 50 MB, 1,000 files, 200 supporting files and 6 million characters. **[auto]**
- [ ] No executables, symlinks, bundled dependencies, hidden files or build leftovers. **[auto]**
- [ ] No hardcoded secrets, personal paths or personal email addresses. **[auto]**
- [ ] No outside checkout or paid-version links (Gumroad, Whop, Lemon Squeezy, Payhip, Ko-fi, Patreon, Stripe
      links). Links to your own repo or docs are fine. **[auto]**

## 3. The eight-point scan (a failed check costs 20 points, a warning 5)

- [ ] File structure, file types, secrets, obfuscation. **[auto]**
- [ ] No `rm -rf /`, `curl | sh`, `os.system`, `shell=True`, `chmod 777`. **[auto]**
- [ ] No environment variables read and sent over the network. No network calls combined with reading local data. **[auto]**
- [ ] No phrases such as "ignore previous instructions", "do not tell the user" or "secretly". **[auto]**
- [ ] Network calls, `sudo`, `base64`, file writes: documented in `SKILL.md` when used. **[auto]**

## 4. `SKILL.md`

- [ ] Frontmatter: `name` (slug, 60 characters at most), `description`. **[auto]**
- [ ] Frontmatter is valid YAML. An unquoted value may not contain `: ` or ` #`. Quote it or use a `>` block. Parse it with
      a real YAML parser before upload: Agensi rejects invalid YAML. **[auto: strict rule]**
- [ ] Description starts with what it does, then `Use when ...` with 3 to 5 trigger phrases, then `Do not use for ...`.
      Under 1,024 characters. **[auto]**
- [ ] The trigger phrases are things a user would actually type ("review this PR", "find the bug"), in quotes, not
      only abstract scenarios. Test them: see `agensi/TRIGGER_TESTS.md`.
- [ ] Single skills also carry `summary` (300 characters at most), `version` (numbers and dots), `tags`, `keywords`,
      `use_cases` and `docs_url`. Limits: 10 tags, 10 keywords, 8 use cases. **[auto]**
- [ ] A defined output format, an edge-case or error section, and steps specific enough to follow. **[auto: headings]**
- [ ] Under 500 lines, details in `references/`. **[auto]**
- [ ] Self-contained: a buyer can use it without reading outside documentation.
- [ ] Every claim in `SKILL.md`, README and listing is true. Run the commands. Check the numbers.
- [ ] At least one reference file or example, and a short README. **[auto: warns]**

## 5. Listing (`agensi/LISTING.md`, checked by the tool) **[auto]**

- [ ] Title 60 characters at most, unique on Agensi (check by opening agensi.io/skills/<slug>).
- [ ] Summary 300 characters at most.
- [ ] Description (Markdown): what it does, how it works, where it stops.
- [ ] "See it in action": a real request and the full real result, 700+ characters. Never invented output.
- [ ] Compatibility note and permissions that match what the scan will detect.
- [ ] 1 to 3 categories from Agensi's list of 32. The first decides the page.
- [ ] Limitations and FAQ.
- [ ] Price: free, or one-time from $1. $5 to $20 converts best. Under $5 buyers pay from balance only.
- [ ] Logo: PNG, square, 512 x 512 recommended, under 5 MB. Up to 6 screenshots under 10 MB each. **[auto]**

## 6. Testing (manual)

- [ ] `TRIGGER_TESTS.md`: the skill triggers on 5 of 5 relevant prompts and 0 of 5 unrelated ones.
- [ ] Output beats the same agent without the skill, on a real project and not a toy.
- [ ] Edge cases: empty input, very large input, odd structure.
- [ ] Tested in at least two agents.
- [ ] After each model update, run the trigger tests again.

## 7. Presentation (the repo)

- [ ] README: one-line pitch, why use it, a real sample, how to run it, how it works, limits, license.
- [ ] One commit, authored by FinnTech3. No other names, no AI attribution, no old-account names. LICENSE names FinnTech3 only.
- [ ] CI is green. Tests pass. Lint is clean.
- [ ] Numbers in the README (test counts, scores) match reality.
- [ ] Nothing in the repo that a buyer cannot use or a reader cannot understand.

## Lessons from past audits

- A lenient YAML check let an invalid description through. Always re-parse the built zip with a real parser.
- An example extracted from a README lost its output. Re-open every generated example and compare it to its source.
- Scripts that worked from the repo failed the delivery model. Always run each script alone from an empty temp folder.
- Lint and tests must be green before pushing, not after.
- Describe the data source honestly (undocumented endpoints, delays, gaps).

## Known limits of the checker

It estimates the scan, it does not run it. It cannot tell whether a skill is good, whether a name is taken, whether
a description triggers, or whether the listing is persuasive. Those are the manual items above.
