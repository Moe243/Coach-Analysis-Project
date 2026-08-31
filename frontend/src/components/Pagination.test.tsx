import { fireEvent, render, screen } from "@testing-library/react";
import { Pagination } from "./Pagination";

describe("Pagination", () => {
  it("uses stable offsets and disables unavailable directions", () => {
    const onChange = vi.fn();
    render(<Pagination total={51} offset={0} limit={25} onChange={onChange} />);
    expect(screen.getByText("1–25 of 51")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Previous page" }),
    ).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "Next page" }));
    expect(onChange).toHaveBeenCalledWith(25);
  });

  it("does not render for a single page", () => {
    const { container } = render(
      <Pagination total={10} offset={0} limit={25} onChange={vi.fn()} />,
    );
    expect(container).toBeEmptyDOMElement();
  });
});
