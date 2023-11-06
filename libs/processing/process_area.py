from Bio import pairwise2
import numpy as np


def check_barcode_area(candidates):
    """Check content of barcode

    Make sure there is at most one object and 
    at least one service found something

    Args:
        candidates (list): list of intersected rectangles

    Returns:
        bool: True if area is ok
    """
    sums = [len(item) for item in candidates]
    return all([i <= 1 for i in sums]) and sum(sums) >= 1


def separate_to_lines(rectangles):
    """Split set of rectangles into lines.

    This is determined by center of rectangle being inside of previous rectangle bounds.

    Args:
        rectangles (list): given list of rectangles

    Returns:
        list of list: list of rectangles grouped to lines
    """
    rectangles.sort(key=lambda rectangle: rectangle.center_y)
    average_height = np.mean([rectangle.height for rectangle in rectangles])
    line_break_threshold = average_height * 0.5

    # Step 3: Group coordinates into lines
    lines = []
    current_line = []
    previous_y = rectangles[0].center_y

    for rectangle in rectangles:
        if abs(rectangle.center_y - previous_y) > line_break_threshold:
            # A line break is detected
            lines.append(current_line)
            current_line = []
        
        current_line.append(rectangle)
        previous_y = rectangle.center_y  # Update previous_y to the bottom of the current word

    # Don't forget to add the last line if it's not empty
    if current_line:
        lines.append(current_line)

    return lines


def get_max_words(groups):
    max_words = 0

    for group in groups:
        for line in group:
            max_words = max(max_words, len(line))

    return max_words


def align_pairwise(string_1, string_2):
    """Align two strings

    TODO: need to be optimised using penalty scores

    Args:
        string_1 (str): first string
        string_2 (str): second string

    Returns:
        str: aligned string
    """
    alignments = pairwise2.align.globalxs(string_1, string_2, -3, -1, gap_char=' ')
    return alignments[0][0]


def majority_vote(strings):
    """Vote on individual positions of identified words

    Args:
        strings (list): list of words (per service) corresponding to a line

    Returns:
        list: most probable list of words
    """
    # Pad strings to the same length
    max_length = max(len(s) for s in strings)
    padded_strings = [s.ljust(max_length) for s in strings]

    # Compute the majority-voted string
    result = []
    for chars in zip(*padded_strings):
        # Count occurrences of each character
        count = {}
        for char in chars:
            count[char] = count.get(char, 0) + 1
        
        # Get the character with maximum occurrence
        voted_char = max(count, key=count.get)
        result.append(voted_char)

    return ''.join(result)


def identify_words(lines):
    """Identify words from lines.
    Behaves differently based on how many lines there are.

    TODO The case when there are only two, some improvements could be done:
    - we can get both directly instead of calling align_pairwise twice
    - voting with two like this makes no sense, perhaps its better to just
      take one of the outputs with no mixing and voting

    Args:
        lines (list): given list of lines as strings

    Returns:
        str: identified word
    """
    if len(lines) == 1:
        return lines[0]
    elif len(lines) == 2:
        align_1 = align_pairwise(lines[0], lines[1])
        align_2 = align_pairwise(lines[1], lines[0])
        return majority_vote([align_1, align_2])
    elif len(lines) == 3:
        results = []
        for i in range(len(lines)):
            this = lines[i]
            other1 = lines[(i+1)%3]
            other2 = lines[(i+2)%3]

            align1 = align_pairwise(this, other1)
            align2 = align_pairwise(this, other2)

            result = align_pairwise(align1, align2)
            results.append(result)
        return majority_vote(results)
    

def filter_exceeding_words(lines, roi):
    """Filter regions exceeding bounds of ROI

    There are three cases:
    1. None of the regions exceeds the bounds
    2. Some of them
    3. All of them

    We keep everything as is in cases 1. and 3.,
    in case 2. we filter out the exceeding ones
    (as at least one of the services thinks the 
    exceeding part does not belong here)

    Args:
        lines (list): given list of lines
        roi (ROI): respective ROI

    Returns:
        list: filtered lines
    """
    indicators = []
    reduced_lines = []
    for line in lines:
        reduced_line = []
        exceeding_indicator = False
        for rectangle in line:
            rectangle_exceeding = roi.exceeding_rectangle(rectangle)
            exceeding_indicator = exceeding_indicator or rectangle_exceeding
            if not rectangle_exceeding:
                reduced_line.append(rectangle)
        indicators.append(exceeding_indicator)
        reduced_lines.append(reduced_line)

    if not (all(indicators) or not any(indicators)):
        return reduced_lines
    return lines


def process_lines(lines, roi):
    """Join lines to words let majority voting decide

    TODO: A smarted algo should be used here at some point,
    working perhaps with individual words and their positions.

    TODO: if majority says there is one item and one service says its two,
    perhaps the majority is right

    Args:
        lines (list): lists of rectangles organised in lines
    """
    lines = filter_exceeding_words(lines, roi)
    lines_of_words = [[rectangle.content for rectangle in line] for line in lines]
    lines_of_words = filter(None, lines_of_words)
    return identify_words([' '.join(line) for line in lines_of_words])


def align_lines(candidate_lines):
    """Group lines to categories by y-coordinate

    Also sort them by y-coordinate to ensure correct order.

    Args:
        candidate_lines (list): identified lines from all services

    Returns:
        list: lines grouped by y-coordinate
    """
    groups = dict()
    for lines in candidate_lines:
        for line in lines:
            center = np.mean([rectangle.center_y for rectangle in line])
            bottom = max([rectangle.end_y for rectangle in line])
            top = min([rectangle.start_y for rectangle in line])

            grouped = False
            for group_center in groups.keys():
                if bottom >= group_center >= top:
                    groups[group_center].append(line)
                    grouped = True
            if not grouped:
                groups[center] = [line]
    
    return [v for _, v in groups.items()]


def general_text_area(candidates, roi):
    """Process text area

    Args:
        candidates (list of lists): identified rectangles intersecting ROI
        roi_coords (tuple): coordinates of the ROI

    Returns:
        str: extracted text
    """
    # seperate each by lines
    candidate_lines = []
    for candidate in candidates:
        if candidate:
            lines = separate_to_lines(candidate)
            for line in lines:
                line.sort()
            candidate_lines.append(lines)

    words = []

    aligned_groups = align_lines(candidate_lines)

    max_words = get_max_words(aligned_groups)

    if len(aligned_groups) <= 3 and max_words <= 5:
        for group in aligned_groups:
            words.append(process_lines(group, roi))
    else:
        for group in aligned_groups:
            words.append(' '.join([rectangle.content for rectangle in group[1]]))

    return '\n'.join(words)
