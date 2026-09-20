# Compact intake screens

These are **headless Textual UI fixtures**, rendered at 80×24 using
`QuestionsScreen` and `PlanScreen` with data from `tests/test_intake_widgets.py`.
They show the actual widgets and keyboard layout, not a live model response or a
completed Jev run. Browser PNGs are screenshots of the corresponding saved SVGs.

The meaningful interaction checks are in `test_intake_widgets.py`: no implicit
answer or execution, recommended display labels versus submitted bare labels,
multiline custom input, backwards edits, pending answers, cancellation, plan
revision, exact prompt display, small-terminal bounds and keyboard scrolling.

The intake runtime and end-to-end model verification are separate from these UI
fixtures. Do not use these images as evidence that a model generated the example.
