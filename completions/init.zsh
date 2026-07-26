# VideoSentinel zsh completion loader.
# Source this from ~/.zshrc, e.g.:
#   source /path/to/VideoSentinel/completions/init.zsh
#
# Source it AFTER whatever runs compinit (oh-my-zsh, prezto, your own call).
# This file deliberately does not re-run compinit when the completion system
# is already initialized: a second compinit costs ~100-200ms of startup and
# writes its own ~/.zcompdump, which conflicts with the framework's own dump
# file (oh-my-zsh uses ~/.zcompdump-$HOST-$ZSH_VERSION).

# Resolve this file's directory even when sourced.
_vs_completions_dir=${${(%):-%N}:A:h}

# Prepend to fpath so _video_sentinel and _monitor_queue are discoverable.
if [[ ":${fpath[*]}:" != *":$_vs_completions_dir:"* ]]; then
    fpath=("$_vs_completions_dir" $fpath)
fi

# compdef only exists once compinit has run. If a framework already ran it,
# reuse that setup; otherwise initialize the completion system ourselves.
# -u skips the insecure-directory prompt.
if (( ! $+functions[compdef] )); then
    autoload -Uz compinit
    compinit -u
fi

if (( $+functions[compdef] )); then
    # fpath was extended after compinit built its dump, so bind the functions
    # explicitly instead of waiting for the dump to be regenerated.
    autoload -Uz _video_sentinel _monitor_queue
    compdef _video_sentinel video_sentinel.py video-sentinel vs
    compdef _monitor_queue monitor_queue.py
fi

unset _vs_completions_dir
