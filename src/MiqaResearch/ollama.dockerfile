FROM ollama/ollama:latest

RUN ollama serve && \
    sleep 5 && \
    ollama pull gemma3:latest && \
    pkill -x ollama

EXPOSE 11434