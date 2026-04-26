# add_rating Integration Planning

You are tasked with integrating add_rating.py inito the infrastructure. Create a new directory in the backend (src) and split up the file into multiple subcomponents, each with proper pydantic typing and logical grouping. Don't forget proper comments etc. You will then use the frontend agent to create a UI for this, which is its own category (search and move is a distinct feature from dedup). This should also be reflected in the menubar (has its own section). While you're at it, the menubar is kinda jank if you expand/collapse it so fix that too.

You will do this in two stages, one is exploratory, the other is the implementation

## Stage 1: Code Base Review and Exüloration

This section describes what add_rating does on a high level. You will verify this and ask questions on the implementation.

primary Function:
add_rating is capable of go through all .nfo files (XML Format) and update rarings from imdb and tmdb via the imdb_id and tmbd_id and provide a score for each to help decide whether the .nfo decsribes the movie (.mkv, .mp4 etc) it belongs to ar has been assigned incorrectly by KODI and their scrapers which is used for scraping at first place.
to do this the metadata files (.log .txt) are scanned for data like countries, year of when the film was premiered, the actors and their roles, runtime of film from EPG.
Usually all necessary Data like country, year description, runtime of movie can be obteined from the .txt file and a .log file contains recording data about timer, start and end of recording.
However in earlier versions of the recordingservice there was a .log used for all that data together that was not sructured very well wirth keywords and also varies in what line which content can be found.
That means if a .txt files is not present there is a fallback to extract the necessary data from the .log file.
Some of the data may not be there and the comparison with the .nfo file is incomplete resulting in a lowe score.
Also the .nfo file might miss data like Plot which is the description of the movie that is represented by the .nfo content

Several options allow to enhance its function.
A llm for example helps in case of a low score with comparing plots of the metadata files (.log .txt) that where create by a recording service and the plot field in the corresponding .nfo file
results from the evaluation are written to fields in the .nfo files.
If a score stays low after all methods ahve been used to compare the .nfo content with the metadata files of the movie an option can be activated to rescrape and alter the .nfo to a better matching tmdb/imdb entry.

Another function of the program allows to find the correct imdb/tmdb content matching the video (.mkv) and their metadata file .txt/.log  and add the .nfo files populated with with content from  imdb/tmdb.
Option  "--create-missing-nfo" activates that part

Please verify that this functionality exists within add_rating.py. 

There are also additonal flags like "recursive search" and others thet you can see in the argparse section

Very important is that the current functionality remains 100% the same

## Stage 2

After stage 1 has been completed, you will integrated add_rating.py based on the worked out implementation plan that you have drafted based on the plan.md.
We should both have a server integrated version as well as a CLI tool (which is also relevant for testing.)

## Stage 3 

you find examples for extraction of metadata in the test-data\add_rating folder

