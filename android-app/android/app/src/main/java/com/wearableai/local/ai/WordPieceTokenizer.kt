package com.wearableai.local.ai

import java.util.Locale

class WordPieceTokenizer(vocabulary: List<String>, private val maxLength: Int = 256) {
    private val ids = vocabulary.withIndex().associate { it.value to it.index }
    private val unknown = ids["[UNK]"] ?: error("Tokenizer vocabulary has no [UNK] token.")
    private val cls = ids["[CLS]"] ?: error("Tokenizer vocabulary has no [CLS] token.")
    private val sep = ids["[SEP]"] ?: error("Tokenizer vocabulary has no [SEP] token.")
    val padId: Int = ids["[PAD]"] ?: 0

    fun encode(text: String): IntArray {
        val tokens = mutableListOf(cls)
        for (word in basicTokens(text)) {
            val wordPieces = pieces(word)
            if (tokens.size + wordPieces.size >= maxLength) break
            tokens += wordPieces
        }
        tokens += sep
        return tokens.toIntArray()
    }

    private fun basicTokens(text: String): List<String> =
        text.lowercase(Locale.ROOT).replace(Regex("""([^\p{L}\p{N}])"""), " $1 ")
            .trim().split(Regex("""\s+""")).filter(String::isNotBlank)

    private fun pieces(word: String): List<Int> {
        ids[word]?.let { return listOf(it) }
        val result = mutableListOf<Int>()
        var start = 0
        while (start < word.length) {
            var end = word.length
            var found: Int? = null
            while (end > start) {
                val piece = (if (start == 0) "" else "##") + word.substring(start, end)
                found = ids[piece]
                if (found != null) break
                end--
            }
            if (found == null) return listOf(unknown)
            result += found
            start = end
        }
        return result
    }
}
