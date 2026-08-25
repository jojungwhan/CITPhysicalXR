import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { FabricSetupProgress } from "./FabricSetupProgress.js";

describe("FabricSetupProgress", () => {
  const steps = [
    { label: "장치 찾기", targetId: "device-discovery" },
    { label: "수업 선택", targetId: "lesson-setup" },
    { label: "장치 배정", targetId: "device-setup" },
    { label: "안전 확인", targetId: "lesson-safety" },
    { label: "수업 진행", targetId: "live-controls" },
  ];

  it("renders one compact navigation path without repeating the current panel title", () => {
    const html = renderToStaticMarkup(
      <FabricSetupProgress
        ariaLabel="수업 준비 진행 상황"
        currentStep={1}
        steps={steps}
      />,
    );

    expect(html).toContain('class="fabric-setup-progress"');
    expect(html).toContain('href="#device-discovery"');
    expect(html).toContain('aria-current="step"');
    expect(html.match(/<li/g)).toHaveLength(5);
    expect(html).not.toContain("교실 장치 찾기");
    expect(html).not.toContain("장치 검색 단계로 이동");
    expect(html).not.toContain("<button");
  });

  it("marks prior steps complete and keeps later steps pending", () => {
    const html = renderToStaticMarkup(
      <FabricSetupProgress
        ariaLabel="Lesson setup progress"
        currentStep={3}
        steps={steps}
      />,
    );

    expect(html.match(/class="is-complete"/g)).toHaveLength(2);
    expect(html.match(/class="is-current"/g)).toHaveLength(1);
  });
});
