#!/bin/bash
# Pipeline completa per preparare dataset WRF per Anemoi

set -e  # Exit on error

echo "========================================================================"
echo "ANEMOI-DATASETS PIPELINE - WRF CHAPTER"
echo "========================================================================"
echo ""

# Configurazione
RECIPE_FILE="${1:-wrf_anemoi_recipe.yaml}"
OUTPUT_DATASET="${2:-zarr_anemoi/ailam-an-cima-3km-2023-2023-1h-v1.zarr}"

echo "Configurazione:"
echo "  Recipe file: $RECIPE_FILE"
echo "  Output dataset: $OUTPUT_DATASET"
# Cancella il dataset se già presente
if [ -e "$OUTPUT_DATASET" ]; then
    echo "⚠️  Dataset già presente: $OUTPUT_DATASET"
    echo "   Rimozione in corso..."
    rm -rf "$OUTPUT_DATASET"
fi
echo ""
# Verifica che il file recipe esista
if [ ! -f "$RECIPE_FILE" ]; then
    echo "❌ Errore: recipe file non trovato: $RECIPE_FILE"
    exit 1
fi

echo "------------------------------------------------------------------------"
echo "STEP 1: Creazione Dataset Anemoi"
echo "------------------------------------------------------------------------"
echo ""
echo "Usando anemoi-datasets create per costruire il dataset..."
echo "Nota: Le statistiche vengono calcolate automaticamente durante la creazione"
echo ""

uv run anemoi-datasets create "$RECIPE_FILE" "$OUTPUT_DATASET"

if [ $? -eq 0 ]; then
    echo ""
    echo "✅ Dataset creato con successo!"
else
    echo ""
    echo "❌ Errore durante la creazione del dataset"
    exit 1
fi

echo ""
echo "------------------------------------------------------------------------"
echo "STEP 2: Ispezione Dataset"
echo "------------------------------------------------------------------------"
echo ""

uv run anemoi-datasets inspect "$OUTPUT_DATASET"

if [ $? -eq 0 ]; then
    echo ""
    echo "✅ Ispezione completata!"
else
    echo ""
    echo "❌ Errore durante l'ispezione"
    exit 1
fi

echo ""
echo "------------------------------------------------------------------------"
echo "STEP 3: Verifica Output"
echo "------------------------------------------------------------------------"
echo ""

if [ -e "$OUTPUT_DATASET" ]; then
    echo "✅ Dataset trovato: $OUTPUT_DATASET"
    
    # Mostra dimensione
    SIZE=$(du -sh "$OUTPUT_DATASET" | cut -f1)
    echo "   Dimensione: $SIZE"
    
    # Conta i file zarr
    if [ -d "$OUTPUT_DATASET" ]; then
        NUM_FILES=$(find "$OUTPUT_DATASET" -type f | wc -l)
        echo "   File zarr: $NUM_FILES"
    fi
else
    echo "❌ Dataset non trovato: $OUTPUT_DATASET"
fi

echo ""
echo "========================================================================"
echo "PIPELINE COMPLETATA!"
echo "========================================================================"
echo ""
echo "Dataset generato: $OUTPUT_DATASET"
echo ""
echo "Prossimi passi:"
echo "  1. Il dataset è pronto per l'uso con anemoi-training"
echo "  2. Usa 'uv run anemoi-datasets inspect $OUTPUT_DATASET' per dettagli"
echo "  3. Consulta ANEMOI_README.md per la documentazione"
echo ""
