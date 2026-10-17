# Shipping and postage quotes

Twelve tasks in which the agent gets a price quote for mailing something: a letter, a package, or a large box, within Canada, within the US, across the border, or overseas. They run on the public rate tools of four carriers: USPS, Canada Post, UPS and Purolator. No account, payment or CAPTCHA is involved. Released V1/V2 and framework code are unchanged.

Mailing a package is an everyday errand that the existing corpora do not cover. It also isolates something agents are known to get wrong: the physical details. The tasks give weights and sizes the way people actually state them, and the carrier's form wants them in its own way. Getting the quote right means:

- **Converting units.** A 2.5 kg package on a calculator that defaults to pounds and ounces; a 4.5 lb, 12 x 10 x 8 in box on a form that sends grams and centimetres.
- **Classifying the item.** Package versus Large Package (any side over 12 in), letter versus large envelope, and a square envelope that USPS surcharges as nonmachinable.
- **Mapping dimensions to fields.** Length is the longest side; width and height go into the right boxes.
- **Choosing the destination type.** Domestic, US ZIP code, or an international country picker.
- **Multi-step forms.** UPS's two-step address-then-package flow with a customs value for a cross-border shipment; Canada Post's wizard; Purolator's non-default weight unit.

The evaluated outcome is initiation of the correctly configured price request. Buying postage, printing a label or booking a pickup is never required, and nothing the agent does here has a side effect: every request is a price lookup.

## Tasks

| Task | Carrier | Request intercepted | What it tests |
| --- | --- | --- | --- |
| `usps_domestic_package_pounds_ounces` | USPS | `GET /Calculator/MailServices` | Package shape; weight split into 3 lb 4 oz |
| `usps_large_package_with_dimensions` | USPS | `GET /Calculator/MailServices` | Large Package rule; rectangular dimensions in inches |
| `usps_package_weight_in_kilograms` | USPS | `GET /Calculator/MailServices` | 2.5 kg into a pounds-and-ounces form |
| `usps_square_envelope_letter` | USPS | `GET /Calculator/MailServices` | Letter, not large envelope; square envelope flag (`ct4=True`) |
| `canada_post_domestic_parcel_metric` | Canada Post | `GET /find-a-rate/price` | Postal codes; metric weight and dimensions |
| `canada_post_parcel_to_us_imperial_units` | Canada Post | `GET /find-a-rate/price` | US ZIP destination; pounds and inches to grams and centimetres |
| `canada_post_international_parcel_to_uk` | Canada Post | `GET /find-a-rate/price` | International country picker |
| `canada_post_domestic_lettermail` | Canada Post | `GET /find-a-rate/lm/price` | Letter or document, not package |
| `ups_toronto_to_new_york_package` | UPS | `POST /ctc/results` | Two-step form; customs value; package spec in inches and pounds |
| `ups_domestic_canada_kilograms` | UPS | `POST /ctc/results` | Kilogram unit selector; domestic Canada |
| `purolator_toronto_to_montreal_pounds` | Purolator | `POST /estimate/api/estimate` | Postal-code lookup; pound weight |
| `purolator_toronto_to_vancouver_kilograms` | Purolator | `POST /estimate/api/estimate` | Changing the default weight unit to kilograms |

The origin is Toronto (M5S 2H7) for every Canadian shipment, consistent with the benchmark persona. US-only USPS tasks use US ZIP codes.

## How the requests are matched

Every price request is a read, so a wrong one is harmless and the matchers can be strict:

- **USPS and Canada Post** carry every input in the query string. The `url_pattern` requires each constrained parameter, in any order, and rejects a duplicated one, in the same style as the environmental-observation suite.
  - Numbers accept equivalent formats (`3`, `3.0`).
  - Where the task needs a unit conversion, the pattern accepts a tolerance band instead of one value. A 2.5 kg USPS package is accepted as 5 lb with 8.x oz, or as 88.x oz; the calculator's own metric conversion sends `p=5&o=8.1856`. A 4.5 lb Canada Post package is accepted as 2030 to 2052 g; the site's conversion sends 2041.17 g. These bands allow reasonable rounding by an agent that converts by hand, and they reject a unit error, such as 4.5 kg or a 2.5 lb package.
- **UPS** sends a form-encoded POST. The `body` filter requires the origin, destination, customs value, packaging, weight, weight unit and dimensions. The address step POSTs to the same URL before any weight exists; requiring `weight1` keeps that earlier request from counting.
- **Purolator** sends JSON. On page load the tool fires a warm-up estimate to the same endpoint with a fixed Toronto address (`M9V3Y1`). The `body` filter requires the real sender, receiver and shipment blocks, so the warm-up never matches. The sender and receiver city and province come from Purolator's own postal-code lookup, so they are deterministic.

Shipping dates are not constrained, so the tasks stay valid on any run date.

## Validation

**Live interception: 12/12.** Each task was run with `clawbench-run <task> --human` in the official base runtime, built from this repository at `07eb50a`. The carrier's UI was then operated over CDP inside the container: page, fields, buttons, as an agent would. Every run ended with the interceptor blocking the task's final price request, and `run-meta.json` recording `intercepted: true`. The exact captured requests are in `tests/fixtures/shipping_quotes_live_captures.json`.

| Task | Run (UTC, 2026-10-17) | `interception.json` SHA-256 (prefix) |
| --- | --- | --- |
| `usps_domestic_package_pounds_ounces` | 22:31:06 | `c8e4bbd18f3456fd` |
| `usps_large_package_with_dimensions` | 22:32:13 | `0837549095d0b040` |
| `usps_package_weight_in_kilograms` | 22:33:24 | `8c36f7bcaa54f433` |
| `usps_square_envelope_letter` | 22:34:19 | `d1228295cdab1baf` |
| `canada_post_domestic_parcel_metric` | 22:35:30 | `8162090af9a375cc` |
| `canada_post_parcel_to_us_imperial_units` | 22:36:35 | `d06c661612037847` |
| `canada_post_international_parcel_to_uk` | 22:37:56 | `3b9b2aa9ff2e61b2` |
| `canada_post_domestic_lettermail` | 22:39:11 | `f2b4096855531933` |
| `ups_toronto_to_new_york_package` | 22:40:24 | `b2d199ea645c3e0f` |
| `ups_domestic_canada_kilograms` | 22:41:57 | `e7f9c5627c968a7c` |
| `purolator_toronto_to_montreal_pounds` | 22:43:24 | `5f85cb27f116731a` |
| `purolator_toronto_to_vancouver_kilograms` | 22:44:19 | `9da6527c882094cd` |

In separate exploratory sessions, the same request shapes returned real prices. USPS listed Priority Mail, Ground Advantage and others for a 3 lb 4 oz package. Canada Post returned Regular Parcel $36.17, Xpresspost $84.39 and Priority $129.28 for 3.2 kg, 40 x 30 x 20 cm, Toronto to Vancouver. UPS returned its services with prices, such as UPS Worldwide Express at 197.07 CAD, billable weight 7.0 lb, for the Toronto to New York package. Purolator returned courier estimates from Ground at $80.20 to Express at $121.36 for 5 lb, Toronto to Montreal.

**Offline checks: 74** (`tests/test_shipping_quotes_suite.py`, run in CI):
- schema and runner validation;
- each live capture matches its own task and no other task;
- equivalent formats and reasonable conversion rounding are accepted;
- near misses are rejected:
  - wrong shape (Package, Large Package, Letter, large envelope);
  - a missing nonmachinable flag;
  - unit errors (kg read as lb, inches entered as cm, grams off by 10x);
  - wrong origin, destination or country;
  - intermediate wizard steps (`ShapeAndSize`, `LargePackageProperties`, `LetterProperties`);
  - a letter priced as a parcel;
  - UPS's first-step POST;
  - Purolator's warm-up call;
  - a duplicated parameter;
  - the wrong HTTP method.
- A mutation check also passed: removing the shape constraint, the nonmachinable flag, the UPS weight fields, or the Purolator address blocks each made the suite fail.

**Verification environment.** The shipped PurelyMail key is revoked ([#384](https://github.com/TIGER-AI-Lab/ClawBench/issues/384)), so these local runs replaced mailbox creation with an unprovisioned address. No task here uses email. On Windows the runtime scripts were normalised to LF line endings before building the image. Neither change touches the runtime server or the interceptor, and neither is part of this PR. These runs cover request interception only: no model ran, and the Stage 2 judge was not exercised.

## Limits

- **Live tools change.** Carriers redesign their calculators. A changed URL or field name shows up as a task that no longer intercepts, and the offline fixtures make the expected request explicit for whoever updates it.
- **UPS echoes postal codes as typed.** The UPS body filter is exact, so its instructions ask for the postal codes exactly as written (`M5S 2H7`, `T2P 1J9`).
- **Purolator matches the whole shipment block.** Adding dimensions or options changes it, so its instructions ask to leave them unset.
- Prices change over time, and the tasks do not depend on them.

## Running

```bash
uv run clawbench-batch --models <model> --cases-dir test-cases/shipping-quotes --all-cases
uv run clawbench-run test-cases/shipping-quotes/usps_package_weight_in_kilograms --human
```
