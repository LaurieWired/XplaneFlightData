# Makefile for X-Plane MFD and Flight Calculators
# Supports both JSF-compliant and non-compliant versions

# --------------------------------------------------
CXX = g++
# JSF-compliant flags: strict warnings, optimization, C++20
CXXFLAGS_COMPLIANT = -std=c++11 -O3 -Wall -Wextra -Wpedantic -Werror -Icompliant -fno-exceptions -fno-rtti
# Non-compliant flags: standard C++20, less strict
CXXFLAGS_NON_COMPLIANT = -std=c++20 -O3 -Wall -Wextra
# Default to compliant version
COMP ?= 1
# Calculator names
TARGETS = wind_calculator flight_calculator turn_calculator vnav_calculator density_altitude_calculator
# Arguments for each calculator
turn_calculator_ARGS = 250 25 90
vnav_calculator_ARGS = 35000 10000 100 450 -1500
density_altitude_calculator_ARGS = 5000 25 150 170
flight_calculator_ARGS = 250 245 90 95 220 0.65 35000 35000 -500 75000 5 120 250 0.82
wind_calculator_ARGS = 90 85 270 15
# AV Rule   3: Max cyclomatic complexity per function: 20
# AV Rule   1: Max non-comment lines of code per function: 200
# AV Rule 110: Max parameters per function: 7
LIZARD_PARAMS := -C20 -Tnloc=200 -a7
# Set this to .exe in Windows to avoid rebuilds when the source files aren't changed.
ifeq ($(findstring Windows,$(OS)),Windows)
O_EXT = .exe
endif
# --------------------------------------------------

O_DIR_PARENT = build
COMP ?= 1
ifeq (COMP,0)
CXXFLAGS = $(CXXFLAGS_NON_COMPLIANT)
SRC_DIR = non-compliant
O_DIR = $(O_DIR_PARENT)/non-compliant
else
CXXFLAGS = $(CXXFLAGS_COMPLIANT)
SRC_DIR = compliant
O_DIR = $(O_DIR_PARENT)/compliant
endif
TARGETS := $(TARGETS)
O_TARGETS := $(addsuffix $(O_EXT), $(TARGETS))
O_DIR_TARGETS := $(addprefix $(O_DIR)/, $(O_TARGETS))


.PHONY: all clean test test-% lizard lizard_w run help

all: $(O_DIR_TARGETS)

$(O_DIR):
	@mkdir -p $(O_DIR)

$(O_DIR)/%$(O_EXT): $(SRC_DIR)/%.cpp | $(O_DIR)
	$(CXX) $(CXXFLAGS) -o $@ $<

clean:
	@echo "Cleaning build artifacts..."
	rm -rf $(O_DIR_PARENT)
	rm -rf __pycache__
	rm -f *.pyc
	@echo "Clean complete!"

test-%: $(O_DIR)/%$(O_EXT)
	@echo "===================================="
	@echo "Running test for: \"$*\" with input: \"$($*_ARGS)\""
	@./$(O_DIR)/$* $($*_ARGS) | ./testcase$(O_EXT) ./tests/$*.txt || (echo "Error in testcase $*" && exit 1)
	@echo "OK"
	@echo "===================================="

# Test all C++ calculators with example data
test: $(addprefix test-, $(TARGETS))
	@echo "===================================="
	@echo "All tests complete!"
	@echo "===================================="

lizard:
	@lizard $(SRC_DIR)/ $(LIZARD_PARAMS)

lizard_w:
	@lizard code/ $(LIZARD_PARAMS) -w

run: $(O_DIR) $(O_DIR_TARGETS)
	@echo "Launching X-Plane MFD..."
	@py aircraft_mfd.py

help:
	@echo "make"
	@echo "    all:      Compiles all files"
	@echo "    clean:    Deletes pycache files and the build folder"
	@echo "    help:     Displays this message"
	@echo "    test:     Tests if the output matches with the corresponding testfile"
	@echo "    test-%:   Tests the % program individually"
	@echo "    lizard:   Displays information about the length and complexity of the files and functions"
	@echo "    lizard_w: Only displays warnings about the length and complexity of the files and functions"
	@echo "    run:      Runs aircraft_mfd.py"
	@echo ""
	@echo "Optional parameters"
	@ehco "    COMP: If not 0, build the compliant version"