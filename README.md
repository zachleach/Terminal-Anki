# anki

A minimal spaced repetition system using vim as the flashcard interface.

## Background

Anki is a flashcard application that uses spaced repetition to help you remember things. You create flashcards with a question and answer, review them by seeing the question and recalling the answer, then rate how well you remembered. Based on your rating, Anki schedules when you'll see that card again—cards you know well appear less frequently, cards you struggle with appear more often.

The problem is that Anki has its own interface for creating and reviewing cards. If you take notes in a text editor like vim, you have to copy and paste content into Anki separately. This project eliminates that friction by bringing spaced repetition to the terminal—your notes are your flashcards, and you create and review them in the same place.

## Overview

Flashcards are stored as plain text files. Each card is a "question-answer chunk" - a block of text starting with `?` on the first line (the question), followed by the answer on subsequent lines.

The system tracks review schedules in a SQLite database, keyed by the SHA-256 hash of each question line.

## File Format

Flashcards are plain text files. Each card starts with `?` on the first line (the question), followed by the answer on subsequent lines. A chunk continues until the next `?` or end of file—trailing blank lines are trimmed.

The intended workflow is to summarize concepts in your own words, then create question/answer pairs for periodic self-testing:

```
Summary of the concept in my own words explaining the key ideas
and relationships I need to understand for this topic.

---

?    What is X?
...answer explaining X

?    How does Y relate to Z?
...answer explaining the relationship

?    Why is this important?
...answer with reasoning
```

## Scheduling

Spaced repetition works by showing you cards at increasing intervals. When you remember something correctly, you won't see it again for a while. When you forget, you see it again soon. This optimizes for long-term retention—you spend more time on material you're struggling with and less time on material you already know.

This system uses a fixed interval schedule:

```txt
[0, 1, 3, 7, 14, 28, 56] days
          ↑
```

If you answer correctly today while at the 7-day interval, you won't see that card again for 14 days. If you forget, the interval resets to 0 and you review it again today.

New cards are due immediately.

## Vim Interface

Cards are displayed in vim using stdin mode (`vim -`), which reads text from a pipe into a buffer. The review loop pipes each card's content to vim and uses a startup command to delete everything below the first line—hiding the answer while showing only the question.

To reveal the answer, press `<Space>` which runs `:earlier 99999h`. This undoes all changes since the buffer was loaded, restoring the deleted answer text.

To record your response, vim exits with a specific code using `:cq N`. The exit code tells the review script how you performed:

| Key       | Action                              |
|-----------|-------------------------------------|
| `<Space>` | Reveal answer (`:earlier 99999h`)   |
| `<Enter>` | Correct—advance to next interval    |
| `1`       | Wrong—reset interval to 0           |
| `-`       | Skip—due tomorrow                   |
| `:q`      | Quit session                        |

### vimrc Configuration

These mappings only trigger in stdin mode (`vim -`), so they won't affect normal vim usage:

```vim
autocmd StdinReadPost * nnoremap <buffer> 1 :cq 1<CR>
autocmd StdinReadPost * nnoremap <buffer> <CR> :cq 2<CR>
autocmd StdinReadPost * nnoremap <buffer> - :cq 3<CR>
autocmd StdinReadPost * nnoremap <buffer> <Space> :earlier 99999h<CR>
```

## Directory Structure

The system expects `~/anki` as the root directory. Organize flashcard files however you want:

```
~/anki/
├── cs4384/
│   ├── context-free-languages/
│   │   ├── cfg-to-cnf.txt
│   │   └── pumping-lemma.txt
│   └── finite-automata/
│       ├── dfa-minimization.txt
│       └── nfa-to-dfa.txt
├── japanese/
│   ├── grammar.txt
│   └── vocabulary.txt
└── anki.db
```

Running `anki` displays due counts per file:

```
.
├── cs4384/
│   ├── context-free-languages/
│   │   ├── cfg-to-cnf.txt 3
│   │   └── pumping-lemma.txt 0
│   └── finite-automata/
│       ├── dfa-minimization.txt 1
│       └── nfa-to-dfa.txt 0
├── japanese/
│   ├── grammar.txt 5
│   └── vocabulary.txt 12
```

## Usage

```bash
# Show due counts (defaults to ~/anki)
anki

# Show due counts for specific directory
anki path/to/dir

# Review due cards in a file
anki file.txt

# Custom study (no scheduling, review all cards)
anki -f file.txt

# Reset schedule for a file (cards become due immediately)
anki --forget file.txt
```

## Pseudocode

### Review Session

```
review_file(filepath):
    chunks = parse_chunks_from_file(filepath)

    for chunk in chunks:
        hash = sha256(first_line_of(chunk))

        if not is_due(hash):
            continue

        exit_code = display_in_vim(chunk)
        schedule_index = get_schedule_index(hash)

        if exit_code == 0:
            break  # user quit
        else if exit_code == 1:  # wrong
            set_schedule(hash, index=0)
        else if exit_code == 2:  # correct
            set_schedule(hash, index=schedule_index + 1)
        else if exit_code == 3:  # skip
            set_due_date(hash, tomorrow)
```

### Due Date Calculation

```
INTERVALS = [0, 1, 3, 7, 14, 28, 56]

set_schedule(hash, index):
    index = min(index, len(INTERVALS) - 1)
    due_date = today + INTERVALS[index] days
    db.upsert(hash, due_date, index)

is_due(hash):
    if hash not in db:
        return true
    return db[hash].due_date <= today
```

### Display Tree (custom vibecoded recursive tree command output)

```
display_due_tree(path):
    delete_orphaned_db_entries(path)

    walk_directory(dir, prefix=""):
        entries = sorted non-hidden .txt files and directories
        for entry in entries:
            if directory:
                print connector + name + "/"
                walk_directory(entry, new_prefix)
            else:
                count = count_due_in_file(entry)
                print connector + name + " " + count

    print "."
    walk_directory(path)
```
