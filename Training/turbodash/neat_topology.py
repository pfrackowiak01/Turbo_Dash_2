from __future__ import annotations

from typing import Any

from neat.graphs import feed_forward_layers


def species_id_for_genome(species_set, genome_id: int) -> int | None:
    for species_id, species in species_set.species.items():
        if genome_id in species.members:
            return int(species_id)
    return None


def genome_topology(genome, config, *, species_id: int | None = None) -> dict[str, Any]:
    genome_config = config.genome_config
    enabled = [key for key, connection in genome.connections.items() if connection.enabled]
    disabled_count = len(genome.connections) - len(enabled)
    output_keys = set(genome_config.output_keys)
    hidden_count = sum(key not in output_keys for key in genome.nodes)
    try:
        layers = feed_forward_layers(
            genome_config.input_keys,
            genome_config.output_keys,
            enabled,
        )
        layer_count = len(layers)
    except RuntimeError:
        layer_count = None
    return {
        "genome_id": int(genome.key),
        "species_id": species_id,
        "enabled_connection_count": len(enabled),
        "disabled_connection_count": disabled_count,
        "genome_node_gene_count": len(genome.nodes),
        "total_node_count": len(genome_config.input_keys) + len(genome.nodes),
        "hidden_node_count": hidden_count,
        "input_count": len(genome_config.input_keys),
        "output_count": len(genome_config.output_keys),
        "feed_forward_layer_count": layer_count,
    }
