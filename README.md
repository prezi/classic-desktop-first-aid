# classic-desktop-first-aid

Tool to fix issues with the Prezi Classic desktop application:
- if you have upgraded from an older macOS version to Catalina or newer, and you have local presentations
- if you have `.flv` files in your local presentations that cannot be synced
- if you have missing images in your local presentations that cannot be synced


### Usage

To run the fixes, please follow these instructions:
- download this repository by clicking on the "Code" button and then "Download ZIP". <img src="https://user-images.githubusercontent.com/5681029/176889875-05c72216-188c-4306-a06e-64d43442cb38.png" height="300px"/>
- unzip the downloaded file
- open the `Terminal` application, and go to the directory you have just unzipped:
  ```bash
  cd Downloads/classic-desktop-first-aid-master
  ```
- run the script:
  ```bash
  python3 fix-local-presentations.py
  ```
  The script will discover your presentations, and apply the fixes. It also creates some backup files, and it will inform you how to run it in case you need to restore the previous state.
