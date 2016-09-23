#!/bin/bash

_swclicomplete()
{
    COMPREPLY=( $( \
            COMP_LINE=$COMP_LINE  COMP_POINT=$COMP_POINT \
            COMP_WORDS="${COMP_WORDS[*]}"  COMP_CWORD=$COMP_CWORD \
            sw-cli bash_completion
        ) )
}

complete -F _swclicomplete sw-cli
