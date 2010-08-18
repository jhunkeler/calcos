#! /usr/bin/env python

from __future__ import division         # confidence high
import os
import sys
import string
import getopt

import numpy as np
import pyfits

import calcosparam                      # parameter definitions
import cosutil
import getinfo
import extract
import timetag

first_message = True                    # initial values

__version__ = calcosparam.CALCOS_VERSION_NUMBER
__vdate__   = calcosparam.CALCOS_VERSION_DATE

def main (args):
    """This is a driver to perform 1-D extraction for one file.

    The input is a corrtag file name (the complete name, e.g.
    rootname_corrtag_a.fits, not just a rootname).  One or more input
    files may be specified.
    The suffixes _corrtag, _flt and _counts are assumed by the code,
    so the files on disk must have these suffixes.
    """

    if len (args) < 1:
        print "Specify one or more input corrtag file names."
        prtOptions()
        raise RuntimeError

    try:
        (options, pargs) = getopt.getopt (args, "qvuo:",
                                          ["find", "location=", "extrsize="])
    except Exception, error:
        print error
        prtOptions()
        raise RuntimeError

    if len (options) == 0:
        for i in range (len (pargs)):
            if pargs[i][0] == '-':
                prtOptions()
                raise RuntimeError, \
                "Command-line options must precede the input file name(s)."

    outdir = None               # output directory name
    update_input = False        # update keywords in corrtag files?
    find_target = False
    location = None
    extrsize = None
    for i in range (len (options)):
        if options[i][0] == "-q":
            cosutil.setVerbosity (calcosparam.QUIET)
        elif options[i][0] == "-v":
            cosutil.setVerbosity (calcosparam.VERY_VERBOSE)

        elif options[i][0] == "-u":
            update_input = True

        elif options[i][0] == "-o":
            outdir = options[i][1]

        elif options[i][0] == "--find":
            find_target = True

        elif options[i][0] == "--location":
            values = options[i][1].split()
            location = []
            for i in range (len (values)):
                if values[i].lower() == "none":
                    location.append (None)
                else:
                    location.append (float (values[i]))

        elif options[i][0] == "--extrsize":
            values = options[i][1].split()
            extrsize = []
            for i in range (len (values)):
                if values[i].lower() == "none":
                    extrsize.append (None)
                else:
                    extrsize.append (int (values[i]))

    extractSpec (pargs, outdir, update_input,
                 location, extrsize, find_target)

def extractSpec (inlist=[], outdir=None, update_input=False,
                 location=None, extrsize=None, find_target=False,
                 verbosity=None):
    """Extract a 1-D spectrum from each set of flt and counts images.

    @param inlist: names of input corrtag files
    @type inlist: list of strings
    @param outdir: name of output directory, or None
    @type outdir: string or None
    @param update_input: if True, update keywords in the input corrtag files
    @type update_input: boolean
    @param location: location(s) at which to extract spectrum or spectra
    @type location: float, or a list of floats
    @param extrsize: extraction height(s) for spectra
    @type extrsize: integer, or a list of integers
    @param find_target: if True, search for the target spectrum in the
        Y direction, rather than relying on the wavecal offset (shift2)
    @type find_target: boolean
    @param verbosity: if not None, set verbosity to this level (0, 1, 2)
    @type verbosity: int or None
    """

    if verbosity is not None:
        if verbosity < 0 or verbosity > 2:
            raise RuntimeError, \
                "Verbosity %d is out of range (0, 1, or 2)" % verbosity
        cosutil.setVerbosity (verbosity)

    cal_ver = calcosparam.CALCOS_VERSION

    if outdir:
        outdir = os.path.expandvars (outdir)
        if not os.path.isdir (outdir):
            raise RuntimeError, \
                "The specified output directory doesn't exist:  %s" % outdir
    else:
        outdir = ""

    # Get the names of the input (corrtag), intermediate (flt, counts, x1d_ab),
    # and output (x1d) files.
    filenames = makeFileNames (inlist, outdir)

    # Now check whether any input file is missing or any intermediate or
    # output file already exists.
    missing = checkMissing (filenames)
    already_exists = checkExists (filenames)
    if missing or already_exists:
        raise IOError

    keys = filenames.keys()
    keys.sort()
    for x1d in keys:
        corrtag_list = filenames[x1d]["corrtag"]
        flt_list = filenames[x1d]["flt"]
        counts_list = filenames[x1d]["counts"]
        x1d_ab_list = filenames[x1d]["x1d_ab"]
        nfiles = len (corrtag_list)
        for i in range (nfiles):
            printFilenames (corrtag_list[i], flt_list[i], counts_list[i],
                            x1d_ab_list[i])
            is_wavecal = makeFltCounts (cal_ver, corrtag_list[i],
                                        flt_list[i], counts_list[i])
            extract.extract1D (flt_list[i], counts_list[i], x1d_ab_list[i],
                               location=location, extrsize=extrsize,
                               find_target=find_target)

        # For FUV, merge the x1d_a.fits and x1d_b.fits files to x1d.fits.
        concatenateSegments (x1d_ab_list, x1d)

        if is_wavecal:
            extract.recomputeWavelengths (x1d)

        # Copy keywords from the x1d file to input files.
        updateSomeKeywords (x1d, filenames, update_input)

def checkMissing (filenames):
    """Check for missing input files.

    @param filenames: names of input and output files
    @type filenames: dictionary

    @return: list of input corrtag files that are not present
    @rtype: list
    """

    missing = []
    for x1d in filenames:
        corrtag_list = filenames[x1d]["corrtag"]
        for corrtag in corrtag_list:
            if not os.access (corrtag, os.R_OK):
                missing.append (corrtag)
    if missing:
        if len (missing) == 1:
            cosutil.printError ("The following input file is missing:")
            cosutil.printContinuation (missing[0])
        else:
            cosutil.printError ("The following input files are missing:")
            for corrtag in missing:
                cosutil.printContinuation (corrtag)

    return missing

def checkExists (filenames):
    """Check for output files that already exist.

    @param filenames: names of input and output files
    @type filenames: dictionary

    @return: list of output files that already exist
    @rtype: list
    """

    already_exists = []

    keys = filenames.keys()
    keys.sort()
    for x1d in keys:
        flt_list = filenames[x1d]["flt"]
        counts_list = filenames[x1d]["counts"]
        x1d_ab_list = filenames[x1d]["x1d_ab"]
        # Separate loops are used here to control the order of names
        # in `already_exists`.
        for i in range (len (flt_list)):
            if os.access (flt_list[i], os.R_OK):
                already_exists.append (flt_list[i])
        for i in range (len (counts_list)):
            if os.access (counts_list[i], os.R_OK):
                already_exists.append (counts_list[i])
        for i in range (len (x1d_ab_list)):
            if os.access (x1d_ab_list[i], os.R_OK):
                already_exists.append (x1d_ab_list[i])
        if x1d != x1d_ab_list[0]:               # FUV data?
            if os.access (x1d, os.R_OK):
                already_exists.append (x1d)

    if already_exists:
        if len (already_exists) == 1:
            cosutil.printError ("The following output file already exists:")
            cosutil.printContinuation (already_exists[0])
        else:
            cosutil.printError ("The following output files already exist:")
            for filename in already_exists:
                cosutil.printContinuation (filename)
        cosutil.printError ("Output files will not be overwritten.")

    return already_exists

def printFilenames (corrtag, flt, counts, x1d_ab):
    """Print the names of the files."""

    global first_message

    if not cosutil.checkVerbosity (cosutil.VERBOSE):
        return

    if not first_message:
        cosutil.printMsg ("")

    names = [("Input", corrtag),
             ("OutFlt", flt),
             ("OutCounts", counts),
             ("x1d", x1d_ab)]
    cosutil.printFilenames (names)
    cosutil.printMsg ("")

    first_message = False

def makeFileNames (inlist, outdir=""):
    """Replace suffixes to make the names of all files that we will need.

    The output is the dictionary `filenames`:
        key is the rootname_x1d.fits file name
        value is a dictionary:
            key is "corrtag", "flt", "counts", or "x1d_ab"
            value is a list of one (NUV) or two (FUV) file names
    For FUV the names in x1d_ab will have suffix "_x1d_a" or "_x1d_b", while
    for NUV the name in x1d_ab will be the same as the key in `filenames`.

    The flt, counts, x1d_ab, and x1d file names all include the output
    directory name (if any).

    @param inlist: list of input corrtag file names
    @type inlist: list
    @param outdir: name of the directory for output files, or ""
    @type outdir: string

    @return: the names of the input and output files
    @rtype: dictionary
    """

    filenames = {}
    for input in inlist:

        corrtag = os.path.expandvars (input)
        i = corrtag.rfind ("corrtag")
        if i < 0:
            raise RuntimeError, "File name " + input + \
                  " was expected to have suffix 'corrtag'"
        # This is the corrtag file name, but in the output directory.
        outdir_input = os.path.join (outdir, os.path.basename (corrtag))

        flt = replaceSuffix (outdir_input, "_corrtag", "_flt")
        counts = replaceSuffix (outdir_input, "_corrtag", "_counts")
        x1d_ab = replaceSuffix (outdir_input, "_corrtag", "_x1d")
        i = x1d_ab.rfind ("_x1d_a")
        if i < 0:
            i = x1d_ab.rfind ("_x1d_b")
        if i < 0:                       # NUV file name
            x1d = x1d_ab
        else:                           # FUV file name
            x1d = x1d_ab[:i+4] + x1d_ab[i+6:]   # root_x1d.fits

        if x1d in filenames:
            filenames[x1d]["corrtag"].append (corrtag)
            filenames[x1d]["flt"].append (flt)
            filenames[x1d]["counts"].append (counts)
            filenames[x1d]["x1d_ab"].append (x1d_ab)
        else:
            filenames[x1d] = {
                "corrtag": [corrtag],
                "flt": [flt],
                "counts": [counts],
                "x1d_ab": [x1d_ab]}

    keys = filenames.keys()
    for x1d in keys:
        filenames[x1d]["corrtag"].sort()
        filenames[x1d]["flt"].sort()
        filenames[x1d]["counts"].sort()
        filenames[x1d]["x1d_ab"].sort()

    return filenames

def makeFltCounts (cal_ver, corrtag, flt, counts):
    """Create the flt and counts files.

    @param cal_ver: calcos version number and date
    @type cal_ver: string
    @param corrtag: name of corrected events table
    @type corrtag: string
    @param flt: name of effective count rate file
    @type flt: string
    @param counts: name of count rate file
    @type counts: string

    @return: True if the current exposure is a wavecal, based on EXPTYPE
    @rtype: boolean
    """

    fd = pyfits.open (corrtag, mode="readonly")
    phdr = fd[0].header
    phdr.update ("cal_ver", cal_ver)

    detector = phdr.get ("detector")
    headers = timetag.mkHeaders (phdr, fd[1].header)
    exptime = headers[1].get ("exptime")

    is_wavecal = phdr["exptype"].find ("WAVE") >= 0

    events = fd[1].data
    x = events.field ("XFULL")
    y = events.field ("YFULL")
    epsilon = events.field ("EPSILON")
    dq = events.field ("DQ")
    if detector == "FUV":
        npix = (calcosparam.FUV_Y, calcosparam.FUV_EXTENDED_X)
        x_offset = calcosparam.FUV_X_OFFSET
    else:
        npix = (calcosparam.NUV_Y, calcosparam.NUV_EXTENDED_X)
        x_offset = calcosparam.NUV_X_OFFSET

    # Create the data quality array.
    info = getinfo.getGeneralInfo (phdr, headers[1])
    info["corrtag_input"] = True
    switches = getinfo.getSwitchValues (phdr)
    reffiles = getinfo.getRefFileNames (phdr)
    timetag.setActiveArea (events, info, reffiles["brftab"])
    minmax_shift_dict = timetag.getWavecalOffsets (events,
                                info, reffiles["xtractab"])
    dq_array = timetag.doDqicorr (events, corrtag, info, switches, reffiles,
                                  phdr, headers[1], minmax_shift_dict)

    timetag.writeImages (x, y, epsilon, dq,
                         phdr, headers, dq_array, npix, x_offset, exptime,
                         counts, flt)

    fd.close()

    return is_wavecal

def concatenateSegments (x1d_ab_list, x1d):
    """Concatenate the 1-D spectra for the two FUV segments into one file.

    If the input list `x1d_ab_list` contains a file name that is the same
    as `x1d` (should be only one name in the list in this case, i.e. NUV
    data), this function will return without doing anything.

    If the list contains just one file name, the file will be renamed;
    otherwise, the files will be concatenated into one file, given by `x1d`.

    @param x1d_ab_list: rootname_x1d_a.fits, rootname_x1d_b.fits file names
    @type x1d_ab_list: list
    @param x1d: rootname_x1d.fits file name
    @type x1d: string
    """

    nfiles = len (x1d_ab_list)

    for i in range (nfiles):
        if x1d_ab_list[i] == x1d:
            return

    if nfiles == 1:
        cosutil.renameFile (x1d_ab_list[0], x1d)
    else:
        extract.concatenateFUVSegments (x1d_ab_list, x1d)

def updateSomeKeywords (x1d, filenames, update_input=False):
    """Copy extraction location keywords from x1d.fits to other files.

    @param x1d: name of the rootname_x1d.fits file
    @type x1d: string
    @param filenames: names of input and output files
    @type filenames: dictionary
    @param update_input: True if we should update keywords in the corrtag files
    @type update_input: boolean
    """

    file_list = []
    x1d_ab = filenames[x1d]["x1d_ab"]
    if len (x1d_ab) > 1:
        file_list.extend (x1d_ab)
    file_list.extend (filenames[x1d]["flt"])
    file_list.extend (filenames[x1d]["counts"])
    if update_input:
        file_list.extend (filenames[x1d]["corrtag"])

    copyKeywords (x1d, file_list)

def copyKeywords (x1d, file_list):
    """Copy extraction location keywords to other headers.

    @param x1d: name of the x1d.fits file (containing both segments, if FUV)
    @type x1d: string
    @param file_list: names of the files (e.g. x1d_a.fits, x1d_b.fits)
        in which header keywords should be updated
    @type file_list: list
    """

    fd1 = pyfits.open (x1d, mode="readonly")

    if fd1[0].header["detector"] == "FUV":
        keywords = ["sp_loc_a", "sp_loc_b",
                    "sp_off_a", "sp_off_b",
                    "sp_nom_a", "sp_nom_b",
                    "sp_slp_a", "sp_slp_b",
                    "sp_hgt_a", "sp_hgt_b",
                    "b_bkg1_a", "b_bkg1_b",
                    "b_bkg2_a", "b_bkg2_b",
                    "b_hgt1_a", "b_hgt1_b",
                    "b_hgt2_a", "b_hgt2_b"]
    else:
        keywords = ["sp_loc_a", "sp_loc_b", "sp_loc_c",
                    "sp_off_a", "sp_off_b", "sp_off_c",
                    "sp_nom_a", "sp_nom_b", "sp_nom_c",
                    "sp_slp_a", "sp_slp_b", "sp_slp_c",
                    "sp_hgt_a", "sp_hgt_b", "sp_hgt_c",
                    "b_bkg1_a", "b_bkg1_b", "b_bkg1_c",
                    "b_bkg2_a", "b_bkg2_b", "b_bkg2_c",
                    "b_hgt1_a", "b_hgt1_b", "b_hgt1_c",
                    "b_hgt2_a", "b_hgt2_b", "b_hgt2_c"]

    for filename in file_list:
        # check that the file still exists (might have been renamed)
        if os.access (filename, os.R_OK):
            fd2 = pyfits.open (filename, mode="update")
            for key in keywords:
                value = fd1[1].header.get (key, -999.)
                fd2[1].header.update (key, value)
            fd2.close()

    fd1.close()

def prtOptions():
    """Print a list of command-line options and arguments."""

    print "The command-line arguments and options are:"
    print "  -q (quiet)"
    print "  -v (very verbose)"
    print "  -u (update keywords in input corrtag files)"
    print "  -o outdir (output directory name)"
    print "  --find (find Y location of spectrum)"
    print "  --location Y location(s) at which to extract spectra"
    print "  --extrsize height(s) of extraction region(s)"
    print "  one or more corrtag file names"

def replaceSuffix (rawname, suffix, new_suffix):
    """Replace the suffix in a raw file name.

    @param rawname: a file name
    @type rawname: string
    @param suffix: suffix part of rootname to be replaced
    @type suffix: string
    @param new_suffix: the string to replace suffix in rawname
    @type new_suffix: string

    @return: rawname with suffix replaced by new_suffix
    @rtype: string
    """

    lenraw = len (rawname)
    lensuffix = len (suffix)
    i = rawname.rfind (suffix)
    if i >= 0:
        newname = rawname[0:i] + new_suffix + rawname[i+lensuffix:]
    else:
        raise RuntimeError, \
            "File name " + rawname + " was expected to have suffix " + suffix

    return newname

if __name__ == "__main__":

    main (sys.argv[1:])