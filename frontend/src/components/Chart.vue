<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount, watch } from "vue";
import * as echarts from "echarts/core";
import { LineChart, PieChart } from "echarts/charts";
import {
  GridComponent,
  TooltipComponent,
  LegendComponent,
} from "echarts/components";
import { CanvasRenderer } from "echarts/renderers";
echarts.use([
  LineChart,
  PieChart,
  GridComponent,
  TooltipComponent,
  LegendComponent,
  CanvasRenderer,
]);
const props = defineProps<{ option: any }>();
const el = ref<HTMLElement>();
let chart: echarts.ECharts;
let observer: ResizeObserver;
onMounted(() => {
  chart = echarts.init(el.value);
  chart.setOption(props.option);
  observer = new ResizeObserver(() => chart.resize());
  observer.observe(el.value!);
});
watch(
  () => props.option,
  () => chart?.setOption(props.option, true),
  { deep: true },
);
onBeforeUnmount(() => {
  observer?.disconnect();
  chart?.dispose();
});
</script>
<template>
  <div ref="el" class="chart" role="img" aria-label="실제 검사 데이터 차트" />
</template>
