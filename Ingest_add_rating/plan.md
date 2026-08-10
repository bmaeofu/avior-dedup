# add_rating Integration Planning

You are tasked with integrating add_rating.py inito the infrastructure. Create a new directory in the backend (src) and split up the file into multiple subcomponents, each with proper pydantic typing and logical grouping. Don't forget proper comments etc. You will then use the frontend agent to create a UI for this, which is its own category (search and move is a distinct feature from dedup). This should also be reflected in the menubar (has its own section). While you're at it, the menubar is kinda jank if you expand/collapse it so fix that too.

You will do this in two stages, one is exploratory, the other is the implementation

## Stage 1: Code Base Review and Exüloration

This section describes what add_rating does. You will verify this and ask questions on the implementation.

primary Function:
see **add_rating_description.md**

Please verify that this functionality exists within add_rating.py. 

Very important is that the current functionality remains 100% the same

## Stage 2

After stage 1 has been completed, you will integrat add_rating.py based on the worked out implementation plan that you have drafted based on the plan.md.
We should both have a server integrated version as well as a CLI tool (which is also relevant for testing.)

## Stage 3 

you find examples for extraction of metadata in the test-data\add_rating folder

