# AI Coach Interaction Contract

## Submission interaction repair

The right panel owns submission. A project-practice lesson with a saved practiceTask shows that exact task, required files, acceptance criteria, optional explanation and the workspace submission action. The center presents teaching and points to the right panel. Passing a text answer never completes a code task. Only a passed course submission unlocks the next code lesson; its submission ID is retained for result retrieval.

The coach turn is a separate text-answer activity. Its reflectionPrompt must be answerable in the text input using the supplied lesson materials. Allowed evidence types are reflection, reading and transfer (a written hypothetical application). It must not request file edits, running tests or supplying execution results. Code authoring/debugging belongs to an explicit file-bound task. The server rejects incompatible generated types rather than saving text as coding evidence. Generated-course text answers are evaluated against the exact question before recording completion; failed evaluation or transport errors do not mark completion.

Existing `course` lessons without practiceTask can explicitly prepare a task from their saved exercise. The task is persisted in lesson-tasks, bound to the lesson content digest and reused on later visits. It uses the existing workspace submission and static evaluation service. Changed lesson content invalidates the task. Imported projects retain coach-exercise provenance; this preparation endpoint does not convert them into course-task submissions. Automatic execution remains unavailable.

The right-side AI Coach is not a collection of fixed quiz text. A Skill/Markdown package defines the durable teaching contract: target capability, learner level, language/runtime context, prerequisites, misconceptions, evidence rubric and safety boundary.

For each lesson turn, the Python gateway may ask the configured model to generate one bounded prediction question, 2–4 answer options, concise feedback and a learner re-explanation prompt. The model must use only the selected Skill assets, the current lesson, the learning focus currently visible in Trainer, its supporting code slice, and voluntarily recorded learning evidence. For a generated project course, `ProjectLesson.exercise` (the center-column “观察与练习” content) is the primary coach focus; the code slice is supporting material and must not silently replace that focus. It must not invent a new curriculum objective, bypass prerequisites, claim mastery, or execute code.

The same structured response must classify the evidence requested by the question as exactly one of: `reflection` (explain a concept), `reading` (interpret supplied code), `writing` (author code), `debugging` (diagnose using an observed result), or `transfer` (apply the idea in a different context). Trainer displays this classification but never asks the learner to choose it. Classification does not prove that the evidence is valid; validation remains a separate step.

Every response must remain tied to the current Skill and lesson. When the model is unavailable, Trainer uses a clearly labeled local fallback derived from the same lesson contract; it never pretends that fallback text was model-generated.

Question, feedback, reflection prompt and evidence classification form one atomic turn. They must target the same concrete learning action. When the visible focus contains several numbered exercises, one turn selects exactly one of them and preserves its file, function, result or failure context. Changing the evidence label without changing the question does not count as synchronization.
