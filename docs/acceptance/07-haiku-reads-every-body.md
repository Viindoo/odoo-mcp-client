# Scenario 7 - haiku reads every body

**Setup.** Every rewritten agent body and skill body of the plugin.

**Run.** Launch a `haiku` agent per file with the instruction: "Read this file as the agent it
describes. For each step, answer in one sentence what you do next. Mark any step where two
readings are possible or where a word like large, small, enough, complex or when needed has no
closed criterion."

**Measure:** the list of steps with two readings per file.

**Pass when** every answer names a single action and the list is empty; a non-empty list is a
defect in that file, fixed before the release.
