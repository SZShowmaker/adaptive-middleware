"""Shared user interactions for the optional browser suites."""
def choose_output_type(page, ref):
    name, version = ref.split('@')
    page.locator('#outputTypeSearch').fill(name)
    page.get_by_role('button', name=name+' @'+version, exact=True).click()
