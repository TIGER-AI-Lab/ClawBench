# Bengali-language web tasks

Every V1 and V2 task runs on an English-language page. This category adds 12 read-only tasks on Bengali-language websites from Bangladesh. To pass, the agent must read a Bengali interface, type Bengali text, and choose options by their Bengali labels, including Bengali numerals such as ১০০. Bengali has about 240 million native speakers, so this is everyday web use for a large group of users.

The base image had no Bengali font, so Bengali text rendered as empty boxes and screenshot-based agents could not read it. This change adds `fonts-noto-core` to `Dockerfile.base`. The package also covers Devanagari, Arabic, Thai, and other scripts. The image grows by about 40 MB.

## Tasks

| Task | Site | What the agent must get right |
|---|---|---|
| `bnwiki_article_history_100` | bn.wikipedia.org | Find রবীন্দ্রনাথ ঠাকুর, open its history, and choose ১০০ revisions per page. |
| `bnwiki_padma_template_search` | bn.wikipedia.org | Full-text search for পদ্মা, limited to the টেমপ্লেট namespace only, with (প্রধান) removed. |
| `wikisource_tagore_incomplete_shortest` | bn.wikisource.org | List scanned books for রবীন্দ্রনাথ that are অসম্পূর্ণ, sorted by পাতার সংখ্যা, ascending. |
| `banglapedia_padma_article` | bn.banglapedia.org | Go to the article titled পদ্মা নদী through the site search, not full-text search. |
| `accessible_dictionary_bn_bn_nodi` | accessibledictionary.gov.bd | Look up নদী in the Bengali-to-Bengali dictionary. The home button labeled বাংলা থেকে বাংলা returns Bengali-to-English results, so the agent must check what it got. |
| `bdportal_passport_title_sort` | bangladesh.gov.bd | Search পাসপোর্ট, sort by শিরোনাম (উর্ধ্বগামী), show ৫০ items, and add no other filter. |
| `mygov_birth_registration_search` | mygov.bd | Close the notice popup and search the services for জন্ম নিবন্ধন. |
| `bdnews24_health_search_sep2026` | bangla.bdnews24.com | Archive search for ডেঙ্গু in স্বাস্থ্য, 1 to 30 September 2026. |
| `prothomalo_ilish_business_latest` | prothomalo.com | Search ইলিশ, section বাণিজ্য, type টেক্সট, newest first. |
| `daraz_panjabi_price_sort` | daraz.com.bd | Use the Bengali UI, search পাঞ্জাবি, price 500 to 1500, lowest price first. |
| `chaldal_egg_search` | chaldal.com | Use the Bengali UI and search the products for ডিম. |
| `bdjobs_teacher_chattogram` | bdjobs.com | Search শিক্ষক, show ২০ jobs per page, and pick the division চট্টগ্রাম বিভাগ, not the district চট্টগ্রাম. |

Each task ends at one search or listing request. The `eval_schema` checks every choice the instruction names. Tracking and paging parameters that the site sets by itself are not checked. No task logs in, submits a form, or buys anything. Checked values avoid ড়, ঢ়, and য়, because those letters have two valid Unicode encodings.

## Validation

- **Live runs:** every task ran in `clawbench-base`, built from this branch, at commit `d8faa73`. A script drove Chromium through CDP mouse and keyboard events, starting from each site's home page. All 12 runs ended with `eval_matched`.
- **Negative runs:** each task also ran once with one choice wrong (for example, another section, sort, or namespace). None of these 12 runs was intercepted.
- **Offline checks:** 219 checks (41 accept and 178 reject) use the runtime's own `_const_fields_match` and `_parse_body`. The reject cases include each checked value wrong or missing, the default request a page sends on load, the wrong host, path, or method, and repeated parameters.
- **Schema:** all 12 files pass the `validate-task` CI check.

## Limits

- These are scripted UI runs, not human runs. Human completion time was not measured.
- The runs used the same container settings as `docker_run_human`, but not the `clawbench-run` CLI, because the CLI creates a PurelyMail account. No model or harness was run, and the Stage 2 judge was not run.
- The tasks evaluate request initiation, not what the page shows afterward.
- Some Bengali UI choices do not appear in the request: the language toggles on Daraz, Chaldal, and bdjobs. The schema cannot check those choices.
- These are live sites. Popups appear on bangladesh.gov.bd, mygov.bd, and bdjobs.com. Prothom Alo encodes a section as a list of sub-section IDs, which may change. Daraz loads an anti-bot script, but no challenge appeared in our runs.

Claude Code built and validated these tasks under the direction of Shubhashis Roy Dipta.
