# Telegram report design specification

Status: approved for `v0.1.0-beta.1`

## Product job

The Telegram report must support two reading speeds: the first screen should
explain the user's current state and main takeaway in seconds, while the rest
of the message must retain the complete analysis. The report is a reading
surface, not a compact dashboard.

## Information order

The production report uses the **Monochrome Health Editorial** structure:

1. Report title and period.
2. Key-metric table with current value, personal baseline, and change.
3. Main takeaway in a pull quote.
4. The report chart.
5. Complete numbered observations with type, confidence, and evidence count.
6. Recommendations.
7. Personal experiments.
8. Overall reliability.
9. Feedback controls in a separate message.

There is no redundant automatic header before a rich report. Observation
numbers remain because they connect conclusions to feedback controls.

## Daily chart

Daily reports use the approved **Readiness contribution** chart. The metric
table owns current values and personal baselines; the chart must not repeat
that information. Instead, it explains how the available factors changed the
day's exploratory readiness score.

- Output: PNG, 1800 by 1080 pixels.
- Background: `#101416`.
- Primary text: `#F3F5F5`.
- Secondary text: `#AAB5B8`.
- Positive contribution: `#70D7CD`.
- Negative contribution: `#D99A92`.
- A centered zero line separates positive and negative contributions.
- Every bar has a signed point label, so meaning never relies on color alone.
- The header shows the final readiness score and report date.
- The footer shows the 50-point starting value and net contribution.
- No gradients, shadows, decorative borders, stock imagery, or emoji.

The preferred factor order is sleep, resting heart rate, HRV, energy, and
focus. A factor appears only when both its current value and personal baseline
are available. One comparable factor is sufficient to render the chart;
without any comparable factors the chart is omitted and the complete text
report is still delivered. The chart visualizes the same transparent scoring
rules used to produce the readiness score and never asks Claude to invent a
contribution.

Weekly and monthly reports use the same editorial message structure and the
existing period trend charts, restyled to the same palette.

## Data contract

Tables and charts are built only from structured `ReportContext` data. Values
must never be parsed back out of Claude prose. Missing values remain missing.
Claude controls the analytical text, not measured values or chart geometry.

## Localization and accessibility

All visible strings support `APP_LOCALE=en` and `APP_LOCALE=ru`. Product names
remain untranslated. The chart must not communicate meaning through color
alone: marker shapes, labels, values, and the baseline note carry the same
meaning. The fixed dark canvas must remain legible in both light and dark
Telegram themes.

## Delivery and failure behavior

The preferred delivery is one native Telegram Rich Message containing the
table, text, and embedded chart. If Telegram rejects the rich message, the bot
falls back to HTML messages split only at section boundaries and sends the
chart between the main takeaway and observations.

Failure to render or upload a chart must never prevent delivery of the full
text. Feedback controls are sent after either delivery path.

## Acceptance criteria

The regular `test-report` command, without preview scripts, must deliver the
approved report in Russian and English. It must retain every claim,
recommendation, and experiment; contain no report emoji; use structured data
for tables and charts; and fall back to the standard Telegram path after a
rich-message or media failure.
