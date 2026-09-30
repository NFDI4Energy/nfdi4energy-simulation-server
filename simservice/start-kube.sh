#!/bin/bash
minikube start
tmux new-session -d -s mount 'minikube mount /home/cori/simservice-data:/data'
echo "Mount started"


