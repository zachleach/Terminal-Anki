# Terminal Anki

A minimal spaced repetition system using vim as the flashcard interface.

## Background

Anki is a flashcard application that uses spaced repetition to help you remember things. You create flashcards with a question and answer, review them by seeing the question and recalling the answer, then rate how well you remembered. Based on your rating, Anki schedules when you'll see that card again—cards you know well appear less frequently, cards you struggle with appear more often.

The problem is that Anki has its own interface for creating and reviewing cards. If you take notes in a text editor like vim, you have to copy and paste content into Anki separately. This project eliminates that friction by bringing spaced repetition to the terminal—your notes are your flashcards, and you create and review them in the same place.

## Installation

### Requirements

- Python 3.6+
- vim

### Setup

1. Clone or copy this repository to `~/anki`:
   ```bash
   git clone <repo-url> ~/anki
   ```

2. Add to your `~/.bashrc` (or `~/.zshrc`):
   ```bash
   # custom spaced repetition code
   function anki() {
       cd ~/anki && python3 anki.py "$@"
   }
   ```

3. Reload your shell:
   ```bash
   source ~/.bashrc
   ```

4. Add the vim keybindings to `~/.vimrc` (see [vimrc Configuration](#vimrc-configuration) below)

5. Run `anki` to verify installation

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

New cards start at index 1. If you answer correctly on your first review, the card advances to index 2 (3-day interval). If you answer correctly at the 7-day interval, you won't see that card again for 14 days. If you forget at any point, the interval resets to 0 and you review it again today.

## Vim Interface

Cards are displayed in vim using stdin mode (`vim -`), which reads text from a pipe into a buffer. The review loop pipes each card's content to vim and uses a startup command to delete everything below the first line—hiding the answer while showing only the question.

To reveal the answer, press `<Space>` or `<Enter>`. This restores the deleted answer text and appends your original notes below a `---` separator, letting you compare the official answer with your personal summary.

To record your response, vim exits with a specific code using `:cq N`. The exit code tells the review script how you performed:

| Key       | Action                              |
|-----------|-------------------------------------|
| `<Space>` | Reveal answer with notes appended   |
| `<Enter>` | Reveal answer with notes appended   |
| `4`       | Correct—advance to next interval    |
| `1`       | Wrong—reset interval to 0           |
| `-`       | Skip—remains due today              |
| `e`       | Edit source file—no schedule update |
| `<C-z>`   | Undo—restore previous card and state|
| `:q`      | Quit session                        |

**Example of revealed answer:**

Before pressing `<Space>` or `<Enter>`, you see only:
```
?    what is the algorithm for converting CFG to CNF
```

After pressing `<Space>` or `<Enter>`:
```
?    what is the algorithm for converting CFG to CNF
1.    add S_0 -> S
2.    remove rhs non-solitary literals
3.    remove rhs with more than 2x symbols
4.    remove rhs with epsilon
5.    remove rhs with 1x symbols

---

add S0 -> S
remove solitary terminals
remove epsilon transitions
remove binary symbols
remove solo symbols
```

When you press `e`, the review session pauses and opens the source file in vim for editing. After you save and close vim, the file is re-parsed and the review session continues with your edits applied. The current question you were viewing is not scheduled (treated as unanswered), and you won't be re-shown questions you already answered earlier in the session.

When you press `<C-z>` (ctrl-z), the system restores the previous card's database state and re-displays it. If the previous card was new (not yet in the database), undo removes it from the database. Undo only works within the current session—history is cleared when you quit. If there's no history (first card), ctrl-z terminates the review session.

### vimrc Configuration

These mappings only trigger in stdin mode (`vim -`), so they won't affect normal vim usage:

```vim
autocmd StdinReadPost * nnoremap <buffer> 1 :cq 1<CR>
autocmd StdinReadPost * nnoremap <buffer> 4 :cq 4<CR>
autocmd StdinReadPost * nnoremap <buffer> - :cq 3<CR>
autocmd StdinReadPost * nnoremap <buffer> e :cq 2<CR>
autocmd StdinReadPost * nnoremap <buffer> <C-z> :cq 5<CR>
autocmd StdinReadPost * nnoremap <buffer> <Space> :normal! ggjVG"ay<CR>:earlier 99999h<CR>:call append(line('$'), ['', '---', ''])<CR>:normal! G"ap<CR>
autocmd StdinReadPost * nnoremap <buffer> <CR> :normal! ggjVG"ay<CR>:earlier 99999h<CR>:call append(line('$'), ['', '---', ''])<CR>:normal! G"ap<CR>
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

## Workflow Tips

### Using fzf for File Selection

For reviewing flashcards in nested directories, using fzf with sourced keybindings provides a much faster workflow than manually typing file paths. Install fzf and add its keybindings to your shell:

```bash
# Add to ~/.bashrc (or ~/.zshrc)
source /usr/share/doc/fzf/examples/key-bindings.bash
```

With this setup, you can use `Ctrl-T` to fuzzy find any file:

```bash
anki <Ctrl-T>
```

This opens an interactive fuzzy finder where you can type partial matches to quickly locate deeply nested flashcard files without typing the full path.

## Pseudocode

### Review Session

```
review_file(filepath):
    reviewed_hashes = set()
    history_stack = []  # [(hash, prev_state, (question_line, chunk))]

    while true:
        chunks = parse_chunks_from_file(filepath)
        due_chunks = filter chunks where is_due(hash) and hash not in reviewed_hashes

        if no due_chunks:
            break

        due_deque = deque(due_chunks)

        while due_deque is not empty:
            (question_line, chunk) = due_deque.popleft()
            hash = sha256(question_line)
            exit_code = display_in_vim(chunk)

            if exit_code == 0:  # quit
                return
            else if exit_code == 4:  # edit
                open_file_in_vim(filepath)
                break  # re-parse file and continue
            else if exit_code == 5:  # undo
                if history_stack is empty:
                    return  # No history - terminate session
                (prev_hash, prev_state, (prev_line, prev_chunk)) = history_stack.pop()
                restore_schedule_state(prev_hash, prev_state)
                reviewed_hashes.remove(prev_hash)
                # Put current card back, then previous card
                due_deque.appendleft((question_line, chunk))
                due_deque.appendleft((prev_line, prev_chunk))
            else if exit_code in [1, 2, 3]:  # wrong, correct, skip
                prev_state = get_schedule_state(hash)
                history_stack.push((hash, prev_state, (question_line, chunk)))
                update_schedule(hash, exit_code)
                reviewed_hashes.add(hash)
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
