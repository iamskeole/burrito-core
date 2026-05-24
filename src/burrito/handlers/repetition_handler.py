import math
import re
import zlib
from collections import deque

from burrito.common.config import settings
from burrito.types.conversation_token import ConversationToken


class RepetitionHandler:
    def __init__(
        self,
        window_size: int = settings.REPETITION_WINDOW_SIZE,
        min_repeated_footprint: int = settings.REPETITION_MIN_FOOTPRINT,
        min_repeated_words: int = settings.REPETITION_MIN_WORDS,
        entropy_threshold: float = settings.REPETITION_ENTROPY_THRESHOLD,
        entropy_num_chars: int = settings.REPETITION_ENTROPY_NUM_CHARS,
    ):
        """
        :param window_size: How many normalized sentences to remember in history.
        :param min_repeated_footprint: Minimum total repeated sentences to trigger an abort.
        :param min_repeated_words: Minimum number of repeated words for word loop fallback.
        :param entropy_threshold: Zlib compression ratio threshold. If the text compresses
               to less than this ratio (default 15% of original size), it's a guaranteed loop.
        :param entropy_num_chars: Minimum number of text characters to keep in buffer for
               entropy checks.
        """
        self.window_size = window_size
        self.min_repeated_footprint = min_repeated_footprint
        self.min_repeated_words = min_repeated_words
        self.entropy_threshold = entropy_threshold
        self.entropy_num_chars = entropy_num_chars

        # state buffers
        self.history = deque(maxlen=window_size)
        self.buffer = ""
        self.recent_raw_text = ""

        # code block fragmentation tracking
        self.is_inside_code_block = False
        self.backtick_buffer = ""

        # matches newlines OR latin punctuation + space OR CJK and AR punctuation
        self.split_pattern = re.compile(r"\n+|(?<=[.!?؟])\s+|(?<=[。！？])")

        # removes all non-alphanumeric characters (except spaces)
        self.cleanup_pattern = re.compile(r"[^\w\s]")

    def _normalize(self, text: str) -> str:
        """
        Aggressively normalizes text for exact comparison:
        1. Lowercases.
        2. Masks all numbers to 'num' (Fixes index looping).
        3. Strips punctuation.
        4. Normalizes whitespace.
        """
        text = text.lower()
        # mask numbers before removing punctuation to avoid merging
        # actually no, some math scenarios where model can't use tools and
        # needs to do math will be false positives, so we stop replacing digits
        # and fallback on entroipy crashing to detect loops
        # text = re.sub(r"\d+", " <| NUM |> ", text)
        text = self.cleanup_pattern.sub("", text)
        return re.sub(r"\s+", " ", text).strip()

    def process_new_token(self, token: ConversationToken) -> bool:
        """
        Feeds a new token into the detector.
        Returns True immediately if a repetition loop (or entropy crash) is caught.
        """

        # track raw text for entropy checks
        self.recent_raw_text += token.text

        # cap raw text num_chars to maintain ~O(1) memory and cpu speed
        if len(self.recent_raw_text) > self.entropy_num_chars:
            self.recent_raw_text = self.recent_raw_text[-self.entropy_num_chars :]

        if self._is_entropy_crashing():
            return True

        # dance around markdown and code blocks
        self.backtick_buffer += token.text
        if "```" in self.backtick_buffer:
            occurrences = self.backtick_buffer.count("```")
            # odd number of ``` in the buffer, toggle the state
            if occurrences % 2 == 1:
                self.is_inside_code_block = not self.is_inside_code_block

            # keep only the fragment after the last complete ```
            self.backtick_buffer = self.backtick_buffer.split("```")[-1]

        # ignore logical repetition while the model is outputting code/data arrays
        if self.is_inside_code_block:
            self.buffer = ""
            return False

        # --- 3. Normal Sequence Limit Cycle Check ---
        self.buffer += token.text

        # defensive, infinite word loops
        if len(self.buffer) >= self.entropy_num_chars:
            if self._check_buffer_word_loop():
                return True

        segments = self.split_pattern.split(self.buffer)

        # once we have complete sentences/lines
        if len(segments) > 1:
            complete_segments = segments[:-1]

            for seg in complete_segments:
                clean_seg = self._normalize(seg)

                # ignore noise (empty strings or single stray characters)
                if len(clean_seg) > 1:
                    self.history.append(clean_seg)
                    if self._check_limit_cycle():
                        return True

            # keep the unfinished token fragment in the buffer
            self.buffer = segments[-1]

        return False

    def _check_limit_cycle(self) -> bool:
        """
        Dynamically checks for limit cycles using the adaptive footprint formula.
        """
        history_list = list(self.history)
        n = len(history_list)

        if n < 2:
            return False

        for k in range(1, (n // 2) + 1):
            occurrences_needed = max(2, math.ceil(self.min_repeated_footprint / k))
            total_items_needed = k * occurrences_needed

            if n < total_items_needed:
                continue

            pattern = history_list[-k:]
            target_block = history_list[-total_items_needed:]
            match_block = pattern * occurrences_needed

            if target_block == match_block:
                return True

        return False

    def _check_buffer_word_loop(self) -> bool:
        """Fallback for when the model forgets punctuation and loops single words."""
        words = self.buffer.lower().split()
        n = len(words)
        if n < self.min_repeated_words + 1:
            return False

        max_k = min(10, n // 3)
        for k in range(1, max_k + 1):
            pattern = words[-k:]
            if words[-2 * k : -k] == pattern and words[-3 * k : -2 * k] == pattern:
                return True

        return False

    def _is_entropy_crashing(self) -> bool:
        """
        Highly repetitive text compresses at unnatural ratios.
        Normal English compresses to ~45%. Loops crash below entropy_threshold (15%).
        """
        len_recent = len(self.recent_raw_text)
        if len_recent < self.entropy_num_chars:
            return False
        check_text = self.recent_raw_text[-self.entropy_num_chars :]
        # see note in _normalize, we leave numbers as is, zlib should eventually catch
        # check_text = re.sub(r"\d+", "0", check_text) #
        compressed = zlib.compress(check_text.encode("utf-8"))
        compression_ratio = len(compressed) / len(check_text)
        is_crashing = compression_ratio < self.entropy_threshold
        if is_crashing:
            return True  # stupud but helps debug
        return False
