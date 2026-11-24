(() => {
    const cemetery = document.getElementById('id_cemetery');
    const sector = document.getElementById('id_section');
    const sections = JSON.parse(document.getElementById('grave-sections').textContent);
    function updateSections() {
        const previous = sector.value;
        sector.replaceChildren(new Option('---------', ''));
        sections.filter(item => String(item.cemetery_id) === cemetery.value).forEach(item => {
            sector.add(new Option(item.name, item.id));
        });
        sector.value = [...sector.options].some(option => option.value === previous) ? previous : '';
    }
    cemetery.addEventListener('change', updateSections);
    updateSections();
    const occupant = document.getElementById('id_occupant');
    if (!occupant) return;
    const newFields = ['name', 'surname', 'birth_date', 'death_date'];
    function updateOccupant() {
        [...newFields, 'deceased', 'burial_date'].forEach(name => {
            const field = document.getElementById(`id_${name}`);
            const visible = newFields.includes(name) ? occupant.value === 'new' :
                name === 'deceased' ? occupant.value === 'existing' : occupant.value !== 'none';
            field.closest('.field').hidden = !visible;
            field.disabled = !visible;
            field.required = visible;
            const label = field.closest('.field').querySelector('label');
            if (!label.querySelector('.required')) {
                const marker = document.createElement('span');
                marker.className = 'required';
                marker.textContent = ' (wymagane)';
                label.append(marker);
            }
        });
    }
    occupant.addEventListener('change', updateOccupant);
    updateOccupant();
})();
