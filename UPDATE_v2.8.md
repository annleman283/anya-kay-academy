# ANYA KAY Academy v2.8

Polish/UX update based on live testing.

- Student materials are download-only; in-app PDF/PPTX viewer removed.
- Download endpoint opens as an attachment and supports signed Academy links.
- Runtime files stay in `MEDIA_DIR` (Railway Volume `/data/academy_media`).
- Admin uploads stream directly to the server with progress; limit 300 MB.
- Lesson/material/schedule text preserves paragraphs and line breaks.
- Lesson description is visible to students.
- Lesson action order: test/complete -> ask Anya -> notes.
- Larger admin editors and visible burgundy caret/focus state.
- Schedule student view preserves formatting.
- Registration copy references certificate spelling.
- Quiz exit explicitly preserves local progress.
- Home has a clearer “Твой следующий шаг” card and resumes an unfinished quiz.
- Failed final exam shows up to three course areas to review.
- Safer lesson deletion warning; hiding remains the preferred temporary action.
- Existing “Мои ошибки” behavior is unchanged.
- No additional lesson/material activity-event tracking was added.
