# Carica su SuperMUC (Local -> Remote)
# Utilizzo: lrz-put <file_locale> <percorso_remoto_assoluto_o_relativo>
supermuc-put() {
    if [ -z "$1" ] || [ -z "$2" ]; then
        echo "Errore: mancano argomenti."
        echo "Usage: lrz-put <local_path> <remote_full_path>"
        return 1
    fi
    rsync -av -e "ssh -S /tmp/skt-di54coy" "$1" "supermuc:$2"
}

# Scarica da SuperMUC (Remote -> Local)
# Utilizzo: lrz-get <percorso_remoto_assoluto_o_relativo> <destinazione_locale>
supermuc-get() {
    if [ -z "$1" ] || [ -z "$2" ]; then
        echo "Errore: mancano argomenti."
        echo "Usage: lrz-get <remote_full_path> <local_path>"
        return 1
    fi
    rsync -av -e "ssh -S /tmp/skt-di54coy" "supermuc:$1" "$2"
}
