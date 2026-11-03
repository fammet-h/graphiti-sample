<script>
  import { onMount } from 'svelte';
  import cytoscape from 'cytoscape';

  let { graph } = $props();
  let container;
  let cy;

  onMount(() => {
    cy = cytoscape({
      container,
      elements: [],
      style: [
        {
          selector: 'node',
          style: {
            label: 'data(label)',
            'background-color': '#d9eee8',
            'border-color': '#378674',
            'border-width': 2,
            color: '#26343b',
            'font-size': 12,
            'text-wrap': 'wrap',
            'text-max-width': 100,
            width: 76,
            height: 76,
          },
        },
        {
          selector: 'edge',
          style: {
            label: 'data(label)',
            width: 2,
            'line-color': '#91a5b1',
            'target-arrow-color': '#91a5b1',
            'target-arrow-shape': 'triangle',
            'curve-style': 'bezier',
            color: '#34404a',
            'font-size': 9,
            'text-background-color': '#ffffff',
            'text-background-opacity': 1,
            'text-background-padding': 2,
          },
        },
      ],
      layout: { name: 'cose', animate: false },
    });

    return () => cy.destroy();
  });

  $effect(() => {
    const elements = [
      ...graph.nodes.map((node) => ({ data: { id: node.id, label: node.name } })),
      ...graph.edges.map((edge) => ({
        data: { id: edge.id, source: edge.source, target: edge.target, label: edge.name },
      })),
    ];
    if (!cy) return;
    cy.elements().remove();
    cy.add(elements);
    cy.layout({ name: 'cose', animate: false }).run();
  });
</script>

<div class="graph-canvas" bind:this={container}></div>
