import { fireEvent, render, screen } from "@testing-library/react";
import { vi } from "vitest";
import type { ManeuverOut, RouteOptionOut } from "@/lib/api/types";
import { Directions } from "./Directions";

function maneuver(overrides: Partial<ManeuverOut>): ManeuverOut {
  return { instruction: "Continue.", verbal_pre_transition_instruction: null, street_names: [], begin_street_names: [], length_meters: 0, time_seconds: 0, type: 8, type_name: "continue", begin_shape_index: 0, end_shape_index: 0, roundabout_exit_count: null, toll: false, highway: false, ...overrides };
}

const route = {
  route_id: "r1",
  profiles: ["standard"],
  length_meters: 6423,
  estimated_duration_seconds: 618,
  has_highway: false,
  has_toll: true,
  maneuvers: [
    maneuver({ instruction: "Drive east on 17th Street.", street_names: ["17th Street"], length_meters: 1200, type: 1, type_name: "start", begin_shape_index: 0, end_shape_index: 10 }),
    maneuver({ instruction: "Enter the roundabout and take the 2nd exit.", roundabout_exit_count: 2, length_meters: 80, type: 26, begin_shape_index: 10, end_shape_index: 14 }),
    maneuver({ instruction: "Take the ramp.", length_meters: 300, type: 18, begin_shape_index: 14, end_shape_index: 20 }),
    maneuver({ instruction: "You have arrived at your destination.", type: 4, type_name: "destination", begin_shape_index: 20, end_shape_index: 20 }),
  ],
} as unknown as RouteOptionOut;

describe("Directions", () => {
  it("summarises the selected route and shows engine text, road names only when supplied, and distance to the next step", () => {
    render(<Directions route={route} units="km" highlighted={null} onHighlight={() => undefined} profileLabel="Standard route" />);
    expect(screen.getByTestId("directions-summary")).toHaveTextContent("Standard route: 4 steps · 6.4 km · about 10 min without live traffic · includes a toll road");
    const steps = screen.getAllByRole("listitem");
    expect(steps[0]).toHaveTextContent("Drive east on 17th Street. 17th Street");
    expect(steps[0]).toHaveTextContent("1.2 km to next");
    expect(steps[1]).toHaveTextContent("(exit 2)");
    expect(steps[2]).not.toHaveTextContent("undefined");
    expect(steps[3]).toHaveTextContent("You have arrived at your destination.");
    expect(steps[3].querySelector(".distance")).toHaveTextContent("");
    expect(screen.getByText(/not live navigation/)).toBeInTheDocument();
  });

  it("highlights a step on focus and marks it as the current step", () => {
    const onHighlight = vi.fn();
    const { rerender } = render(<Directions route={route} units="km" highlighted={null} onHighlight={onHighlight} />);
    fireEvent.focus(screen.getAllByRole("listitem")[1]);
    expect(onHighlight).toHaveBeenCalledWith(1);
    rerender(<Directions route={route} units="km" highlighted={1} onHighlight={onHighlight} />);
    expect(screen.getAllByRole("listitem")[1]).toHaveAttribute("aria-current", "step");
  });
});
