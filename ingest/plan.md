# Search and Move Integration Planning

You are tasked with integrating searchandmove.py inito the infrastructure. Create a new directory in the backend (src) and split up the file into multiple subcomponents, each with proper pydantic typing and logical grouping. Don't forget proper comments etc. You will then use the frontend agent to create a UI for this, which is its own category (search and move is a distinct feature from dedup). This should also be reflected in the menubar (has its own section). While you're at it, the menubar is kinda jank if you expand/collapse it so fix that too.

You will do this in two stages, one is exploratory, the other is the implementation

## Stage 1: Code Base Review and Exüloration

This section describes what serach and move does on a high level. You will verify this and ask questions on the implementation.

Search and move is capable of looking through files with the ability to specify which contents it should look for within the files. The files could be either txt or xml files. 

Texts to look for / tags can be combined with each other through AND and OR for searches WITHIN THE SAME FILE.

If a file is found that matches the conditions, dpeneding on the set flag (find or move), these found files will be moved into a specified directory. The complete movie set with all subfiles (a movie/episode contains metadata with different file endings under the same name).

Please verify that this functionality exists within the searchandmove.py. 

There are also additonal flags like "recursive search" and others.

## Stage 2

After stage 1 has been completed, you will implement the functionality based on the worked out implementation plan that you have drafed based on the plan.md.
We should both have a server integrated version as well as a CLI tool (which is also relevant for testing.)

## Stage 3 

In the previous search and move, the following parameters lead to a negative and positive case.
in the test-data folder, you can find such files in the respective negative and positive folders. The positive cases are the ones that should be moved according to the criteria, the negative ones are not. 


Positive Test Case Example:

Here is an example of the preivous CLI structure. The paths here do not matter, but the criteria does. We want to use the criteria for the test cases. Please ensure after implementation that the tests pass here.


            "args": ["m", "\\\\UMS\\media\\transcoded\\check_nfo", "\\\\UMS\\media\\tv\\tobescraped", "-e", ".nfo", "-s", "rating:>5.4&nfostatus:!exists", "rating:>5.4&nfostatus:", "rating:>5.4&nfostatus:nfo file ok", "-o", "check_nfo_comtains_files_for_rescraping.txt"],

