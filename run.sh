#!/bin/bash

# Color codes
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
WHITE='\033[1;37m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Usage
usage() {
    echo "Usage: $0 -f <commands.txt> [-b <batch_size>] [-s]"
    echo "  -f <file>        Path to txt file with commands"
    echo "  -b <batch_size>  Number of commands to run in parallel (default: 1)"
    echo "  -s               Stop on first error"
    exit 1
}

# Parse arguments
BATCH=1
STOP_ON_ERROR=0
while getopts "f:b:s" opt; do
    case $opt in
        f) FILE="$OPTARG" ;;
        b) BATCH="$OPTARG" ;;
        s) STOP_ON_ERROR=1 ;;
        *) usage ;;
    esac
done

if [[ -z "$FILE" ]]; then
    usage
fi

if [[ ! -f "$FILE" ]]; then
    echo "File not found: $FILE"
    exit 1
fi

# Read commands into array
mapfile -t CMDS < "$FILE"
NUM_CMDS=${#CMDS[@]}

# Status arrays
declare -a STATUS
declare -a PIDS
declare -a EXIT_CODES

for ((i=0; i<NUM_CMDS; i++)); do
    STATUS[$i]="WAITING"
    PIDS[$i]=""
    EXIT_CODES[$i]=""
done

# Print status
print_status() {
    tput civis
    tput cup 0 0
    for ((i=0; i<NUM_CMDS; i++)); do
        CMD="${CMDS[$i]}"
        SHORT_CMD="${CMD:0:40}"
        case "${STATUS[$i]}" in
            WAITING)
                echo -ne "${YELLOW}[WAITING]${NC} $SHORT_CMD"
                ;;
            RUNNING)
                echo -ne "${WHITE}[RUNNING]${NC} $SHORT_CMD"
                ;;
            SUCCESS)
                echo -ne "${GREEN}[SUCCESS]${NC} $SHORT_CMD"
                ;;
            FAIL)
                echo -ne "${RED}[FAIL]${NC} $SHORT_CMD | ExitCode : ${EXIT_CODES[$i]}${NC}"
                ;;
        esac
        echo -ne "\033[K\n"
    done
    tput el
    tput cnorm
}

clear
print_status

running_count=0
finished=0

while (( finished < NUM_CMDS )); do
    # Launch new commands if possible
    for ((i=0; i<NUM_CMDS; i++)); do
        if [[ "${STATUS[$i]}" == "WAITING" && $running_count -lt $BATCH ]]; then
            STATUS[$i]="RUNNING"
            # print_status
            bash -c "${CMDS[$i]}" >> run.log 2>&1 &
            PIDS[$i]=$!
            ((running_count++))
        fi
    done

    print_status

    # Check running commands
    for ((i=0; i<NUM_CMDS; i++)); do
        if [[ "${STATUS[$i]}" == "RUNNING" ]]; then
            if ! kill -0 "${PIDS[$i]}" 2>/dev/null; then
                wait "${PIDS[$i]}"
                EXIT_CODES[$i]=$?
                if [[ "${EXIT_CODES[$i]}" -eq 0 ]]; then
                    STATUS[$i]="SUCCESS"
                else
                    STATUS[$i]="FAIL"
                    if [[ $STOP_ON_ERROR -eq 1 ]]; then
                        print_status
                        echo -e "${RED}Stopped due to error in command: ${CMDS[$i]}${NC}"
                        # Kill all running
                        for ((j=0; j<NUM_CMDS; j++)); do
                            if [[ "${STATUS[$j]}" == "RUNNING" ]]; then
                                kill "${PIDS[$j]}" 2>/dev/null
                            fi
                        done
                        exit 1
                    fi
                fi
                ((running_count--))
                ((finished++))
                print_status
            fi
        fi
    done
    sleep 0.1
done

print_status
