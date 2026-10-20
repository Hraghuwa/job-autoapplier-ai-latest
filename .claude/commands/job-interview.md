---
description: Interview prep for a tracked application, then a mock interview
argument-hint: <company name>
---
Prepare me for my interview at **$ARGUMENTS** using the `jobagent` MCP tools.

1. `jobagent_list_applications` with search = the company. If several match, ask which one.
2. If its status isn't `interview` yet, ask whether to `jobagent_record_outcome` it as interview (with a note on the stage, e.g. "HR screen Thursday").
3. `jobagent_interview_prep` — built from the resume and note I actually sent. If it returns a brief, write the prep yourself and store it with `jobagent_save_interview_prep`. Show the likely questions with model answers, the company brief and the red flags.
4. Offer a mock interview: ask one question at a time, wait for my answer, then give short feedback (what landed, what to tighten, one stronger phrasing). Never invent experience I don't have.
5. After the real interview, remind me to tell you how it went so you can `jobagent_record_outcome` with the feedback as the note — it feeds the next round's prep.
