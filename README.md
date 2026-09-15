# ANYA KAY Academy v2.7 — BIG UPDATE

Built on the working v2.6 / signed Telegram Academy auth flow. Do not change the educational bot for this update.

## Included
- Final theory exam: 24 supplied questions, shuffled questions/options, pass threshold 70%, unlimited retries, result stored in admin/student profile.
- Successful exam celebration and transition to `Мой график`; no certificate feature.
- Schedule preserves pasted line breaks/paragraphs.
- Note save has visible button state + center-screen confirmation.
- Student admin card: progress by lesson, attempts, best scores, mistakes count, final exam result, last activity, admin note, schedule, unlock lesson, reset lesson test.
- Course admin: create/edit/delete/publish lessons; edit title/description/order; YouTube URL or uploaded lesson video; add/replace/delete lesson materials; edit lesson questions, answers, correct answer, explanation, and question photo.
- Bonus materials admin: add/edit/replace/delete.
- Runtime uploads are outside GitHub.

## Railway media storage — IMPORTANT
Create a Railway Volume for the Academy service and mount it, for example at `/data`.
Set:

`MEDIA_DIR=/data/academy_media`

Without a persistent volume, files uploaded from the admin panel can disappear after a redeploy/restart. Code remains in GitHub; uploaded PPTX/PDF/images/videos stay on the volume.

Existing environment variables remain unchanged: `BOT_TOKEN`, `ADMIN_IDS`, `DB_PATH` etc. Keep the same working values from v2.6.

## Deployment
Upload this build to the **Academy repository only**. Do not replace or redeploy the educational bot code for v2.7. Railway should redeploy the Academy service from GitHub.

## Safety
Before connecting/changing a production DB, keep a backup of the current `lessons.db`. Existing lesson/test data are preserved; v2.7 only adds Academy tables when missing.
