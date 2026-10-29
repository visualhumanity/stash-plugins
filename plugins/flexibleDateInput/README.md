# Flexible Date Input

Adds an "Attempt to fix?" link under Stash's date fields when the entered date is invalid. Clicking it converts common date formats to the `YYYY-MM-DD` format Stash requires.

## Features

- Shows the "Attempt to fix?" link only while a date field reports an invalid date; valid dates get no link.
- Works on every date field built on Stash's date input, including edit forms and bulk edit dialogs.
- Converts `YYYYMMDD` (`20261029`) to `2026-10-29`.
- Reads a plain number as an epoch timestamp in milliseconds (`1793275200000`).
- Hands anything else to the browser's date parser, which handles forms such as `10/29/2026`, `2026/10/29`, `Oct 29, 2026` and `29 October 2026`.
- Replaces the field's value only when the conversion succeeds. Nothing is saved until you save the form.

## Known limitations

- Slash and dash dates are read month first: `01/02/2026` becomes `2026-01-02`, and day-first dates such as `29/10/2026` are not converted.
- Epoch timestamps in seconds (`1793275200`) are read as milliseconds and give a date in 1970.
- The browser's date parser decides which other forms work, so a value converted in one browser may not be in another.
- The result uses your local time zone. A timestamp or date with a time zone (such as an epoch near midnight UTC) can land on the day before or after.
- When a value can't be converted, clicking the link does nothing and shows no message.

## Development

`flexibleDateInput.js` is esbuild output. Its TypeScript source is not in this repo, so edit the built file by hand with care, or rewrite it as plain ES like the other UI plugins. It patches the `DateInput` component with `patch.after` and renders the helper after the original input. There are no tests.
