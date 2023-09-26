import json
import os
import subprocess
import sys
import logging

from langcodes import Language, standardize_tag


class bcolors:
    HEADER = "\033[95m"
    OKBLUE = "\033[94m"
    OKCYAN = "\033[96m"
    OKGREEN = "\033[92m"
    WARNING = "\033[93m"
    FAIL = "\033[91m"
    ENDC = "\033[0m"
    BOLD = "\033[1m"
    UNDERLINE = "\033[4m"

class MStreamHandler(logging.StreamHandler):
    special_code = "[!n]"
    def emit(self, record) -> None:   
        if self.special_code in record.msg:
            record.msg = record.msg.replace( self.special_code, "" )
            self.terminator = ""
        else: self.terminator = "\n"
        return super().emit(record)

def setup_sucess_logging():
    success = logging.getLogger("Sucess")
    success.setLevel(logging.INFO)
    format = ""
    f = logging.Formatter(format)
    ch = logging.StreamHandler()
    ch.setFormatter(f)
    success.addHandler(ch)

setup_sucess_logging()
logging.basicConfig(level=logging.INFO, format="%(levelname)-8s | %(message)s", handlers=[MStreamHandler()])
log_success = logging.getLogger("Sucess")
log_success.propagate = False
__location__ = os.path.realpath(os.path.join(os.getcwd(), os.path.dirname(__file__)))
bins = os.path.join(__location__, "bins\\")

def get_list_of_files():
    logging.debug("Getting files from imported folders")
    filesFolders = list()
    media_list = list()
    for id, multi in enumerate(sys.argv):
        if id != 0: filesFolders.append(sys.argv[id])

    for path in filesFolders:
        if os.path.isfile(path): media_list.append(path)
        else:
            for root, directories, files in os.walk(path):
                for filename in files:
                    file_extension = os.path.splitext(filename)[1]
                    if file_extension in {".mkv"}:
                        filepath = os.path.join(root, filename)
                        media_list.append(filepath)
    return media_list

class ans:
    SDHContains = ["SDH", "sdh", "Sdh", "Closed Captions", "CC", "Full", "full sync", "Full subtitles"]
    SSContains = ["Sign", "signs/songs", "songs", "signs / songs"]

class media_analyzer():
    
    def __init__(self, media_list):
        self.media_list = media_list
        self.media_data = {}
        self.commands = {}
        self.mkvpropedit = os.path.join(bins, "mkvpropedit.exe")
        self.mkvmerge = os.path.join(bins, "mkvmerge.exe")

    def extract_data(self):
        for file in self.media_list:
            filename = os.path.basename(file).replace(".mkv","").replace(".mp4","")
            self.media_data[filename] = {}
            self.media_data[filename]["path"] = file
            info_command = [self.mkvmerge, "-J", file]
            logging.info(f"{bcolors.OKCYAN}{filename}{bcolors.ENDC} is being analyzed... [!n]")
            data = subprocess.run(info_command, stdout=subprocess.PIPE)
            if data.returncode == 0: 
                log_success.info(f"{bcolors.OKGREEN}Success!{bcolors.ENDC}")
                self.media_data[filename]["raw_data"] = json.loads(data.stdout.decode("utf-8"))["tracks"]
                logging.debug(self.media_data[filename])
            else: logging.error(f"{bcolors.FAIL}There was an error while analyzing the file{bcolors.ENDC}")    
        
        return self.media_data

    def parse_data(self):
        for file in self.media_data:
            title = file
            file = self.media_data[title]
            propedit_command = [self.mkvpropedit, file["path"], "-q", "-e","info",
                "-s","title=" + title, "-e","track:v1", "-s","name=" + title]
            
            for track in file["raw_data"]:
                if track["type"] == "audio" or track["type"] == "subtitles":
                    logging.debug(track)
                    trackId = track["id"]+1
                    trackLanguage = Language.get(track["properties"]["language"]).display_name().capitalize()
                    try: trackOldTitle = str(track["properties"]["track_name"])
                    except: trackOldTitle = "Unknown"
                    try: codec = track["properties"]["codec_id"]
                    except: pass
                    trackDefault = "0"
                    try: SDH = track["properties"]["flag_hearing_impaired"]
                    except: SDH = False

                    if track["type"] == "audio":
                        trackChannels = track["properties"]["audio_channels"]
                        if trackLanguage == "English": trackDefault = "1"
                        if trackChannels == 2: trackChannels = "2.0"
                        if trackChannels == 6: trackChannels = "5.1"
                        if trackChannels == 8: trackChannels = "7.1"
                        if codec == "A_FLAC": trackCodecName = "FLAC"
                        if codec == "A_EAC3": trackCodecName = "Dolby Digital Plus"
                        if codec == "A_TRUEHD": trackCodecName = "TrueHD Atmos"
                        if codec == "A_AC3": trackCodecName = "Dolby Digital"
                        if codec == "A_DTS": trackCodecName = "DTS-HD Master Audio"
                        if codec == "A_PCM": trackCodecName = "PCM"
                        if codec == "A_AAC": trackCodecName = "Advanced Audio Coding (AAC)"
                        trackName = trackCodecName + " " + str(trackChannels)
                    
                    if track["type"] == "subtitles":
                        trackName = trackLanguage
                        if SDH or any(x in trackOldTitle for x in ans.SDHContains): trackName += " [SDH]"
                        elif any(x in trackOldTitle for x in ans.SSContains):
                            trackName += " [Sign/Songs]"
                            trackForced = "1"
                        
                        if codec.split("/")[1] == "UTF8": trackCodecName = "SRT"
                        else: trackCodecName = codec.split("/")[1]
                        trackName += f" [{trackCodecName}]"

                    track_command = [
                        "-e","track:" + str(trackId),
                        "-s","name=" + trackName,
                        "-s","flag-default=" + trackDefault
                        ]
                    
                    try: track_command.extend(["-s","flag-forced=" + trackForced])
                    except: pass
                    if SDH: track_command.extend(["-s","flag-hearing-impaired=1"])

                    propedit_command.extend(track_command)

            self.media_data[title]["propedit_command"] = propedit_command

    def edit_files(self):
        propedit_commands = list()
        for file in self.media_data:
            filename = file
            file = self.media_data[filename]
            propedit_commands.append((filename,file["propedit_command"]))
        procs = [ (i[0], subprocess.Popen(i[1], stdout=subprocess.PIPE)) for i in propedit_commands ]
        for p in procs:
            logging.info(f"Writing metadata to {bcolors.OKBLUE}{p[0]}{bcolors.ENDC}... [!n]")
            error = p[1].stdout.read().decode("utf-8").strip()
            p[1].communicate()
            if p[1].returncode == 0: log_success.info(f"{bcolors.OKGREEN}Success!{bcolors.ENDC}")
            else: log_success.error(f"{bcolors.FAIL}There was an error while editing the file\n{error}{bcolors.ENDC}")

def main():
    logging.info(f"{bcolors.OKGREEN}Track renaming script started{bcolors.ENDC}")
    print("")
    media_list = get_list_of_files()
    if media_list == []: 
        logging.warning(f"{bcolors.WARNING}No files imported, exiting the script{bcolors.ENDC}")
        exit()
    analyzer = media_analyzer(media_list)
    logging.info(f"{bcolors.HEADER}Extracting track info from files:{bcolors.ENDC}")
    analyzer.extract_data()
    analyzer.parse_data()
    print("")
    logging.info(f"{bcolors.HEADER}Writing new track info to files:{bcolors.ENDC}")
    analyzer.edit_files()
    print("")
    logging.info(f"{bcolors.OKGREEN}All files have been processed{bcolors.ENDC}")

if __name__ == '__main__':
    main()