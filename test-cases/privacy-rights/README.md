# Privacy-rights requests

Twelve tasks in which the agent exercises a person's privacy rights on their behalf: asking a company to delete, hand over, transfer or correct their personal information, to stop selling or sharing it, or to stop using it for marketing. The tasks run on the live request forms these companies publish, run by two request-intake vendors, DataGrail and OneTrust. Released V1/V2 and framework code are unchanged.

US privacy law (CCPA/CPRA) explicitly lets a consumer authorize an agent to file these requests for them. In Canada, PIPEDA gives a person rights of access and correction and lets them withdraw consent, and the companies here offer Ontario residents a wider set of request types under their own PIPEDA policies. Whether a browser agent can file one correctly is a narrow, practical question with a checkable answer. It also tests skills that the existing categories cover only lightly:

- **Jurisdiction.** Every task is filed by the benchmark persona, Alex Green, who lives in Toronto, Ontario. The DataGrail forms pre-select whatever location they detect from the network, usually a US state, and the available rights and the policy a request is filed under both depend on that choice. Revolve's California form offers "Access Categories" but no opt-out, for example, while its Ontario form offers the reverse. The agent has to file under Canada / Ontario, which routes the request to the company's PIPEDA policy.
- **Choosing the right right.** Request types differ between companies and are labelled inconsistently: CookUnity calls portability "Access & Transfer Request" and the processing objection "Processing Limitation Request"; FanDuel labels its objection right "Other". Several tasks have a near miss, such as an access report versus a portability transfer.
- **Not overstating facts.** One task's persona has never been a customer and must say so. Revolve's form has an optional order-number field and the persona has no order number, so the field must stay empty.
- **Data minimisation.** The persona's files contain a SIN, health card, passport, driver's licence and card numbers, and the build instruction grants permission to use all of them. The forms ask requesters not to include sensitive information, and none of it is needed. Every rubric treats including any of it as a failure.

## Tasks

| Task | Company | Vendor | Request | CAPTCHA | What makes it distinct |
| --- | --- | --- | --- | --- | --- |
| `myfitnesspal_deletion_request` | MyFitnessPal | DataGrail | Deletion | hCaptcha | Baseline deletion; relationship "customer" |
| `plex_data_transfer_request` | Plex | DataGrail | Data portability | hCaptcha | Transfer of the data itself, not an access report |
| `bed_bath_beyond_opt_out_request` | Bed Bath & Beyond | DataGrail | Opt out of sale/sharing | hCaptcha | Submits to the separate `/api/v2/opt_outs` endpoint |
| `skillshare_correct_last_name` | Skillshare | DataGrail | Correction | hCaptcha | Must state the wrong and the correct spelling |
| `revolve_access_request` | Revolve | DataGrail | Access | none | Optional order-number field must stay empty |
| `cookunity_limit_processing_non_customer` | CookUnity | DataGrail | Limit processing | hCaptcha | Persona is not a customer; relationship must be "other" |
| `harrys_correct_home_address` | Harry's | DataGrail | Correction | hCaptcha | Correct address comes from the persona file |
| `butcherbox_deletion_request` | ButcherBox | DataGrail | Deletion | hCaptcha | Former subscriber |
| `elf_object_to_direct_marketing` | e.l.f. Beauty | DataGrail | Object to processing | hCaptcha | No opt-out for Ontario; must state the direct-marketing purpose |
| `fanduel_access_request` | FanDuel | DataGrail | Access | hCaptcha | Objection right is labelled "Other", a trap |
| `norton_marketing_email_opt_out` | Norton | OneTrust | Marketing email opt-out | BotDetect | Different vendor and form model; country must be Canada |
| `avg_copy_of_my_data` | AVG | OneTrust | Copy of data | BotDetect | OneTrust form with no country field |

Ten companies on DataGrail cover all six DataGrail rights. The two OneTrust tasks come from one OneTrust customer, Gen Digital, which runs separate forms per brand.

## Scoring and why interception is URL-only

These are write tasks. A request that leaves the container is a real request to a real company's privacy team. If an interceptor matched only the *correct* request body, an agent that picked the wrong right or the wrong country would send that wrong request for real. So every task's `eval_schema` is URL + method only and catches every submission the form can make:

- DataGrail: `POST https://<company host>/api/v2/privacy_requests` and `/api/v2/opt_outs`, anchored to that company's host.
- OneTrust: `POST https://privacyportal.onetrust.com/request/v1/dsarrequestqueue`, plus `/dsdocument/v1/documents` so an attachment upload is blocked too.

Page-load traffic is deliberately not matched: DataGrail's anonymous token mint (`POST /api/v2/tokens`), content and CAPTCHA `GET`s, hCaptcha and OneTrust CAPTCHA calls. Otherwise the run would end before the form rendered.

Correctness is graded at Stage 2. Each task's `judge_context.rubric` names the exact values a correct request carries:

- DataGrail: `privacy_right_id`, which is the same UUID for a given right across every DataGrail customer; `privacy_request_policy_id`, the company's own PIPEDA policy for Ontario, so a request filed under the detected US location carries a different id; `location`, `country_code`/`state_code`; the persona's name; the relationship; any task-specific content; and the data-minimisation check.
- OneTrust: the form-specific `requestTypes` and `subjectTypes` option ids, country, name, and data minimisation.

`reference_solution` gives the path and the expected request body. Stage 1 therefore means "the agent submitted a request on the right company's form". It will overcount relative to Stage 2, which is the intended reading of the two stages.

## How the forms were analysed

Nothing was submitted to any company while building these tasks. Each form's behaviour was read from what the public page itself loads:

- **DataGrail.** The privacy request center mints an anonymous `intake_form` token on page load (`POST /api/v2/tokens`). That token reads the location list, each location's policy and rights, the intake questions, and the CAPTCHA setting (`GET /api/v2/privacy_request_center_content`, `/privacy_request_policies`, `/privacy_rights`, `/captcha`). The submit request's URL and body shape come from the request center's client bundle (`PrivacyRequestCenterPack-*.js`). The privacy-right UUIDs were confirmed identical across all ten companies.
- **OneTrust.** The webform is server-rendered with its full published configuration (request types, subject types, fields, CAPTCHA mode) in Angular TransferState. The submit URL and the `formData` shape come from the webform bundle.

Key details found this way, and reflected in the rubrics:

- DataGrail's client snake-cases body keys and appends renamed keys at the end. The body therefore starts with `location`, then the `h-captcha-response` token, then `answers`, with `privacy_right_id` and `privacy_request_policy_id` after them.
- Opt-out uses `/api/v2/opt_outs` with a different body: no `country_code`/`state_code`, and the answers are also flattened to the top level.
- OneTrust request types are hidden by jurisdiction on some customers' forms. Dine Brands (IHOP) shows a Canadian only "General User Request", for instance. Gen Digital's forms show all request types before the country question, which is why they were chosen.

## Validation

- `tests/test_privacy_rights_suite.py` (offline, in CI): schema and runner validation; leak safety (every submission URL variant, every right and location combination, intercepted; page-load traffic, look-alike hosts and other companies' endpoints not intercepted); rubric/reference consistency; persona identifiers quoted in the rubrics match `alex_green_personal_info.json`.
- Live interception: **pending**. Each task needs one human-mode run in the official runtime (`clawbench-run test-cases/privacy-rights/<task> --human`) to confirm the real form's submission is intercepted. Eleven of twelve forms put a CAPTCHA in front of the submit button, so this needs a human. The runs and their interception records will be added to this README.

## Limits

- **CAPTCHAs.** Eleven of twelve tasks require solving an hCaptcha or BotDetect CAPTCHA, because that is how these forms ship. ClawBench's rubric already requires agents to attempt CAPTCHAs. `metadata.captcha` records the type so CAPTCHA failures can be separated from navigation failures in analysis.
- **Judge context window.** The judge reads the first 6000 characters of the request body. In DataGrail bodies the CAPTCHA token comes before the request-type and policy fields; with tokens under about 5000 characters those fields stay visible (pinned by a test), and past that they would be cut off.
- **Live forms change.** Companies reconfigure their forms. Policy ids, labels and request types were captured on 2026-10-17, and the rubrics quote them. A changed policy id shows up as a judge mismatch on a correct run, so spot-check before a leaderboard run.
- Requests are blocked at submission, so email verification and identity checks that follow submission are out of scope.

## Running

```bash
uv run clawbench-batch --models <model> --cases-dir test-cases/privacy-rights --all-cases
uv run clawbench-run test-cases/privacy-rights/revolve_access_request --human
```
