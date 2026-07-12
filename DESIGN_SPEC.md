# DESIGN SPEC for MoonshotHunt UI

BASE DIRECTION: Product Hunt's light, card-driven, upvote-centric layout.
Two borrowed elements from a reference image, adapted into our own palette:
a black pill CTA button and a gradient speech-bubble message box.

## COLORS
- Background: #FFFFFF (page), #F8F7F4 (section alternation)
- Text: #1A1A1A (primary), #6B6B6B (secondary), #9B9B9B (muted)
- Borders: #EAEAEA
- Accent (primary, replaces PH orange): coral #D85A30 — upvotes, active
  tags, links, focus states
- Accent (secondary): teal #1D9E75 — verification badges, success states
- Stage badge: amber tint bg #FAEEDA, text #854F0B
- Speech-bubble gradient: #1D9E75 to #0F6E56, diagonal
- CTA button: solid black #111111, hover #2A2A2A, white text

## TYPOGRAPHY
system sans stack. Headlines 28px/600. Card titles 17px/600.
Body 15px/400. Meta text 13px/400 #6B6B6B. No serif/display fonts anywhere.

## SHAPE
12px radius on cards, 10px on inputs/tags, FULL PILL (999px) ONLY
on primary CTA buttons — this is a reserved signature, not a general style.
Card padding 16px. Grid gap 16px. Flat borders, no shadows (PH is flat,
not elevated).

## COMPONENTS
1. Startup card: logo 48x48 (8px radius) left, name + stage badge inline,
   one-line tagline below, sub-theme tag chips, upvote control right
   (arrow + count, coral when active), verification badges, 1px #EAEAEA
   border, no shadow.
2. Primary CTA button: full pill, black bg, white text, trailing arrow
   icon (→), 14px vertical / 28px horizontal padding. Use for "Submit
   your startup →", "Publish listing →". This is the ONLY pill element
   in the system.
3. Message/quote box: speech-bubble shape (16px border-radius, small tail
   bottom-left), teal gradient background, white text 15px, line-height
   1.6. RESERVE for founder-voice moments only (a founder's own quote,
   not generic UI copy).
4. Verification badge: small pill, 1px teal border, teal text, checkmark
   icon. "Unverified" variant uses gray instead of teal. All badge labels
   are LOWERCASE (e.g. "website · unverified", not "Website · unverified").
5. Stage badge: amber pill, shown with EQUAL visual weight at every
   stage including "idea" — no stage should look worse than another.
6. Submission form: single column, 24px vertical gaps between sections,
   uppercase section labels (12px, #9B9B9B, letter-spacing 0.5px), stage
   picker as a horizontal segmented control (not a dropdown) so all
   stages are visible at once.
7. Whitespace map: white canvas, cards cluster by sub-theme proximity
   (not a rigid grid), small floating cluster labels.

DO NOT carry over from the reference image: no decorative
stickers/emoji clusters, no radial background circles, no avatar-orbit
layout — those are specific to that brand, not ours.

## APPLICATION NOTES (implementation)
- Palette tokens (CSS vars):
  --bg:#FFFFFF; --bg2:#F8F7F4; --txt:#1A1A1A; --txt2:#6B6B6B; --mut:#9B9B9B;
  --line:#EAEAEA; --coral:#D85A30; --teal:#1D9E75; --teal2:#0F6E56;
  --amber-bg:#FAEEDA; --amber-tx:#854F0B; --black:#111111; --black2:#2A2A2A.
- Full pill (border-radius:999px) is applied ONLY to .cta (primary buttons).
- Speech-bubble (.quote) gradient + tail is used ONLY for founder-voice quotes.
- Verification badges: label text lowercased in the template/agent layer;
  "verified" => teal, "unverified" => gray (#9B9B9B text, #EAEAEA border).
- Stage badges all use amber pill styling regardless of stage value.
