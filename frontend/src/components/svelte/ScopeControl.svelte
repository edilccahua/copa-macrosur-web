<!--
  ScopeControl.astro / ScopeControl.svelte — el selector "casi escondido".

  Dispara una lista desplazable con el valor actual. Es el mismo control para
  elegir la FECHA (acumulado "a la fecha") y para acotar el ÁMBITO de
  categorías: una sola implementación, dos instancias.

  Patrón visual tomado del selector de etapas de letour.fr (chevron + panel
  desplazable) y traducido a la estética GetArtCraft: hairline de 1px, esquinas
  rectas, mono 11px en mayúsculas y el elemento activo invertido.
-->
<script lang="ts">
  import { onMount } from 'svelte';
  import { fly } from 'svelte/transition';
  import { cubicOut } from 'svelte/easing';

  interface Option {
    value: string;
    label: string;
    meta?: string;
  }

  interface Props {
    options: Option[];
    value: string;
    /** Antetítulo del control (p.ej. "FECHA", "ÁMBITO"). */
    label?: string;
    /** Texto del chevron anterior/siguiente. */
    onchange?: (value: string) => void;
  }

  let { options, value, label = '', onchange }: Props = $props();

  let open = $state(false);
  let activeIndex = $state(0);
  let root = $state<HTMLElement | null>(null);
  /** Con `prefers-reduced-motion` no hay animación: el panel abre y cierra seco. */
  let reduced = $state(false);

  onMount(() => {
    reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  });

  let current = $derived(options.find((o) => o.value === value) ?? options[0]);
  let currentIndex = $derived(options.findIndex((o) => o.value === value));

  function openPanel() {
    open = true;
    activeIndex = currentIndex >= 0 ? currentIndex : 0;
  }

  function closePanel() {
    open = false;
  }

  function toggle() {
    if (open) closePanel();
    else openPanel();
  }

  function select(v: string) {
    closePanel();
    if (v !== value) onchange?.(v);
  }

  function step(delta: number) {
    const next = (currentIndex + delta + options.length) % options.length;
    select(options[next].value);
  }

  function onKeydown(e: KeyboardEvent) {
    if (!open) {
      if (e.key === 'Enter' || e.key === ' ' || e.key === 'ArrowDown') {
        e.preventDefault();
        openPanel();
      }
      return;
    }
    if (e.key === 'Escape') {
      e.preventDefault();
      closePanel();
    } else if (e.key === 'ArrowDown') {
      e.preventDefault();
      activeIndex = (activeIndex + 1) % options.length;
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      activeIndex = (activeIndex - 1 + options.length) % options.length;
    } else if (e.key === 'Enter') {
      e.preventDefault();
      select(options[activeIndex].value);
    }
  }

  function onDocumentClick(e: MouseEvent) {
    if (!open) return;
    if (root && e.target instanceof Node && !root.contains(e.target)) closePanel();
  }
</script>

<svelte:document onclick={onDocumentClick} />

<div class="sc" class:is-open={open} bind:this={root}>
  <div class="sc__head">
    {#if label}<span class="sc__label font-mono">{label}</span>{/if}
    <button
      type="button"
      class="sc__trigger font-mono"
      aria-haspopup="listbox"
      aria-expanded={open}
      onclick={toggle}
      onkeydown={onKeydown}
    >
      <span class="sc__value">{current?.label ?? '—'}</span>
      {#if current?.meta}<span class="sc__meta">{current.meta}</span>{/if}
      <svg class="sc__chev" width="10" height="10" viewBox="0 0 10 10" aria-hidden="true">
        <path d="M1 3.5 L5 7 L9 3.5" fill="none" stroke="currentColor" stroke-width="1.3" />
      </svg>
    </button>
  </div>

  {#if open}
    <ul
      class="sc__panel"
      role="listbox"
      aria-label={label || 'Selector'}
      transition:fly={reduced ? undefined : { y: -4, duration: 150, opacity: 0, easing: cubicOut }}
    >
      {#each options as opt, i (opt.value)}
        <li
          class="sc__item font-mono"
          class:is-active={opt.value === value}
          class:is-cursor={i === activeIndex}
          role="option"
          aria-selected={opt.value === value}
          tabindex="-1"
          onmouseenter={() => (activeIndex = i)}
          onclick={() => select(opt.value)}
        >
          <span class="sc__item-label">{opt.label}</span>
          {#if opt.meta}<span class="sc__item-meta">{opt.meta}</span>{/if}
        </li>
      {/each}
    </ul>
  {/if}
</div>

<style>
  .sc {
    position: relative;
    display: inline-block;
    /* Alias exigido por el brief: el acento activo es el del grupo (--scope-ink). */
    --accent-color: var(--scope-ink, var(--accent));
  }

  .sc__head {
    display: flex;
    align-items: baseline;
    gap: 0.5rem;
  }

  .sc__label {
    font-size: 0.625rem;
    letter-spacing: 0.14em;
    text-transform: uppercase;
    color: var(--faint);
  }

  .sc__trigger {
    display: inline-flex;
    align-items: baseline;
    gap: 0.5rem;
    padding: 0 0 0.15rem;
    background: transparent;
    border: none;
    border-bottom: 1px solid var(--scope-ink, var(--line-strong));
    color: var(--ink);
    font-size: 0.75rem;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    cursor: pointer;
    transition: border-color var(--default-transition-duration) var(--default-transition-timing-function);
  }

  .sc__trigger:hover {
    border-bottom-color: var(--scope-ink, var(--ink));
  }

  /* El foco usa el color del grupo activo (no el azul por defecto del navegador)
     y se separa del resto con un anillo y una sombra. */
  .sc__trigger:focus,
  .sc__trigger:focus-visible,
  .sc.is-open .sc__trigger {
    outline: none;
    border-bottom-color: var(--accent-color);
    box-shadow: 0 1px 0 0 var(--accent-color);
  }

  .sc__trigger:focus-visible {
    outline: 2px solid var(--accent-color);
    outline-offset: 3px;
  }

  .sc.is-open .sc__trigger {
    box-shadow:
      0 1px 0 0 var(--accent-color),
      0 1.25rem 2.5rem -0.75rem rgba(0, 0, 0, 0.55);
  }

  .sc__value {
    font-weight: 700;
  }

  .sc__meta {
    color: var(--muted);
    letter-spacing: 0.06em;
  }

  .sc__chev {
    align-self: center;
    color: var(--muted);
  }

  .sc__panel {
    position: absolute;
    top: calc(100% + 0.35rem);
    right: 0;
    z-index: 50;
    margin: 0;
    padding: 0.25rem 0;
    list-style: none;
    min-width: 13rem;
    max-height: 21rem;
    overflow-y: auto;
    overscroll-behavior: contain;
    background: var(--bg-raised);
    border: var(--hairline) solid var(--line-strong);
    /* Sombra profunda: el panel debe leerse por encima de los badges de la tabla. */
    box-shadow: 0 1.25rem 2.5rem -0.75rem rgba(0, 0, 0, 0.55);
  }

  .sc__panel::-webkit-scrollbar {
    width: 4px;
  }

  .sc__panel::-webkit-scrollbar-thumb {
    background: var(--line-strong);
  }

  .sc__item {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    gap: 1rem;
    padding: 0.4rem 0.75rem;
    font-size: 0.6875rem;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    color: var(--muted);
    cursor: pointer;
  }

  .sc__item.is-cursor {
    background: var(--bg-sunken);
    color: var(--ink);
  }

  .sc__item.is-active {
    background: var(--scope-ink, var(--invert-bg));
    color: #fff;
  }

  .sc__item-meta {
    color: var(--faint);
    letter-spacing: 0.06em;
  }

  .sc__item.is-active .sc__item-meta {
    color: #fff;
    opacity: 0.65;
  }

  @media (max-width: 47.99em) {
    .sc {
      display: block;
      width: 100%;
    }

    .sc__head {
      flex-direction: column;
      align-items: stretch;
      gap: 0.2rem;
    }

    .sc__trigger {
      justify-content: flex-start;
    }

    /* El dato secundario ya está en la línea de metadatos de la cabecera */
    .sc__meta {
      display: none;
    }

    .sc__panel {
      left: 0;
      right: 0;
      min-width: 0;
      max-height: 60vh;
    }
  }
</style>
