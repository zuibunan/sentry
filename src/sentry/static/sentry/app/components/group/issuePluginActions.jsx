import React from 'react';
import _ from 'underscore';
import Modal from 'react-bootstrap/lib/Modal';
import AlertActions from '../../actions/alertActions';
import ApiMixin from '../../mixins/apiMixin';
import {Form, Select2Field, Select2FieldAutocomplete, TextareaField, TextField} from '../../components/forms';
import DropdownLink from '../../components/dropdownLink';
import GroupActions from '../../actions/groupActions';
import GroupState from '../../mixins/groupState';
import LoadingError from '../../components/loadingError';
import LoadingIndicator from '../../components/loadingIndicator';
import MenuItem from '../../components/menuItem';
import {t} from '../../locale';
import {defined, toTitleCase} from '../../utils';

const IssuePlugin = React.createClass({
  propTypes: {
    plugin: React.PropTypes.object.isRequired,
    actionType: React.PropTypes.oneOf(['unlink', 'link', 'create']).isRequired,
    onSuccess: React.PropTypes.func
  },

  mixins: [
    ApiMixin,
    GroupState
  ],

  getInitialState() {
    return {
      createFieldList: null,
      linkFieldList: null,
      loading: _.contains(['link', 'create'], this.props.actionType),
      error: null,
      createFormData: {},
      linkFormData: {}
    };
  },

  componentWillMount() {
    let plugin = this.props.plugin;
    if (!plugin.issue && this.props.actionType !== 'unlink') {
      this.fetchData();
    }
  },

  getPluginCreateEndpoint() {
    return ('/issues/' + this.getGroup().id +
            '/plugin/create/' + this.props.plugin.slug + '/');
  },

  getPluginLinkEndpoint() {
    return ('/issues/' + this.getGroup().id +
            '/plugin/link/' + this.props.plugin.slug + '/');
  },

  getPluginUnlinkEndpoint() {
    return ('/issues/' + this.getGroup().id +
            '/plugin/unlink/' + this.props.plugin.slug + '/');
  },

  setError(error, defaultMessage) {
    let _error;
    if (error.status === 400 && error.responseJSON) {
      _error = error.responseJSON;
    } else {
      _error = {'message': defaultMessage};
    }
    this.setState({error: _error});
  },

  fetchData() {
    this.setState({
      loading: true
    });

    if (this.props.actionType === 'create') {
      this.api.request(this.getPluginCreateEndpoint(), {
        success: (data) => {
          let createFormData = {};
          data.forEach((field) => {
            createFormData[field.name] = field.default;
          });
          this.setState({
            createFieldList: data,
            error: null,
            loading: false,
            createFormData: createFormData
          });
        },
        error: (error) => {
          let state = {
            loading: false
          };
          if (error.status === 400 && error.responseJSON) {
            state.error = error.responseJSON;
          }
          this.setState(state);
        }
      });
    } else if (this.props.actionType === 'link') {
      this.api.request(this.getPluginLinkEndpoint(), {
        success: (data) => {
          let linkFormData = {};
          data.forEach((field) => {
            linkFormData[field.name] = field.default;
          });
          this.setState({
            linkFieldList: data,
            error: null,
            loading: false,
            linkFormData: linkFormData
          });
        },
        error: (error) => {
          let state = {
            loading: false
          };
          if (error.status === 400 && error.responseJSON) {
            state.error = error.responseJSON;
          }
          this.setState(state);
        }
      });
    }
  },

  createIssue() {
    this.api.request(this.getPluginCreateEndpoint(), {
      data: this.state.createFormData,
      success: (data) => {
        GroupActions.groupPluginChange(this.getGroup().id);
        AlertActions.addAlert({
          message: t('Successfully created issue.'),
          type: 'success'
        });
        this.props.onSuccess && this.props.onSuccess();
      },
      error: (error) => {
        this.setError(error, t('There was an error creating the issue.'));
      }
    });
  },

  linkIssue() {
    this.api.request(this.getPluginLinkEndpoint(), {
      data: this.state.linkFormData,
      success: (data) => {
        GroupActions.groupPluginChange(this.getGroup().id);
        AlertActions.addAlert({
          message: t('Successfully linked issue.'),
          type: 'success'
        });
        this.props.onSuccess && this.props.onSuccess();
      },
      error: (error) => {
        this.setError(error, t('There was an error linking the issue.'));
      }
    });
  },

  unlinkIssue() {
    this.api.request(this.getPluginUnlinkEndpoint(), {
      success: (data) => {
        GroupActions.groupPluginChange(this.getGroup().id);
        AlertActions.addAlert({
          message: t('Successfully unlinked issue.'),
          type: 'success'
        });
        this.props.onSuccess && this.props.onSuccess();
      },
      error: (error) => {
        this.setError(error, t('There was an error unlinking the issue.'));
      }
    });
  },

  changeField(action, name, value) {
    let key = action + 'FormData';
    let formData = this.state[key];
    formData[name] = value;
    let state = {};
    state[key] = formData;
    this.setState(state);
  },

  renderField(action, field) {
    let el;
    let required = defined(field.required) ? field.required : true;
    let props = {
      value: this.state[action + 'FormData'][field.name],
      onChange: this.changeField.bind(this, action, field.name),
      label: field.label + (required ? '*' : ''),
      name: field.name,
      disabled: field.readonly,
      help: <span dangerouslySetInnerHTML={{__html: field.help}}/>
    };
    switch (field.type) {
      case 'text':
        el = <TextField {...props} />;
        break;
      case 'textarea':
        el = <TextareaField {...props} />;
        break;
      case 'select':
        if (field.has_autocomplete) {
          props.url = ('/api/0/issues/' + this.getGroup().id +
                       '/plugin/autocomplete/' + this.props.plugin.slug);
          el = <Select2FieldAutocomplete {...props} />;
        } else {
          props.choices = field.choices;
          el = <Select2Field {...props} />;
        }
        break;
      default:
        el = null;
    }
    return el;
  },

  renderForm() {
    let form;
    switch (this.props.actionType) {
      case 'create':
        if (this.state.createFieldList) {
          form = (
            <Form onSubmit={this.createIssue} submitLabel={t('Create Issue')}>
              {this.state.createFieldList.map((field) => {
                return <div key={field.name}>{this.renderField('create', field)}</div>;
              })}
            </Form>
          );
        }
        break;
      case 'link':
        if (this.state.linkFieldList) {
          form = (
            <Form onSubmit={this.linkIssue} submitLabel={t('Link Issue')}>
              {this.state.linkFieldList.map((field) => {
                return <div key={field.name}>{this.renderField('link', field)}</div>;
              })}
            </Form>
          );
        }
        break;
      case 'unlink':
        form = (
          <div>
            <p>{t('Are you sure you want to unlink this issue?')}</p>
            <button onClick={this.unlinkIssue}
                    className="btn btn-danger">{t('Unlink Issue')}</button>
          </div>
        );
        break;
      default:
        form = null;
    }
    return form;
  },

  getPluginConfigureUrl() {
    let org = this.getOrganization();
    let project = this.getProject();
    let plugin = this.props.plugin;
    return '/' + org.slug + '/' + project.slug + '/settings/plugins/' + plugin.slug;
  },

  renderError() {
    let error = this.state.error;
    if (!error) {
      return null;
    }
    if (error.error_type === 'auth') {
      return (
        <div className="alert alert-block">
          <p>You still need to <a href={error.auth_url}>associate an identity</a>
           {' with ' + error.title + ' before you can create issues with this service.'}</p>
        </div>
      );
    } else if (error.error_type === 'config') {
      return (
        <div className="alert alert-block">
            {!error.has_auth_configured ?
                <div>
                  <p>{('Your server administrator will need to configure authentication with ')}
                  <strong>{error.auth_provider}</strong>{(' before you can use this plugin.')}</p>
                  <p>{('The following settings must be configured:')}</p>
                  <ul>{error.required_auth_settings.map((setting) => {
                    return <li><code>{setting}</code></li>;
                  })}</ul>
                </div>
              :
              <p>You still need to <a href={this.getPluginConfigureUrl()}>configure this plugin</a> before you can use it.</p>}
        </div>
      );
    } else if (error.error_type === 'validation') {
      let errors = [];
      for (let name in error.errors) {
        errors.push(<p key={name}>{error.errors[name]}</p>);
      }
      return (
        <div className="alert alert-error alert-block">
          {errors}
        </div>
      );
    } else if (error.message) {
      return (
        <div className="alert alert-error alert-block">
          <p>{error.message}</p>
        </div>
      );
    }
    return <LoadingError/>;
  },

  render() {
    if (this.state.loading) {
      return <LoadingIndicator />;
    }
    return (
      <div>
        {this.renderError()}
        {this.renderForm()}
      </div>
    );
  }
});


const IssuePluginActions = React.createClass({
  propTypes: {
    plugin: React.PropTypes.object.isRequired
  },

  mixins: [
    ApiMixin,
    GroupState
  ],

  getInitialState() {
    return {
      showModal: false,
      actionType: null
    };
  },

  openModal(action) {
    this.setState({
      showModal: true,
      actionType: action
    });
  },

  closeModal() {
    this.setState({
      showModal: false,
      actionType: null
    });
  },

  render() {
    let plugin = this.props.plugin;

    if (!plugin.allowed_actions || !plugin.allowed_actions.length) {
      return null;
    }

    let allowedActions;
    if (plugin.issue) {
      allowedActions = plugin.allowed_actions.filter((action) => { return action === 'unlink'; });
    } else {
      allowedActions = plugin.allowed_actions.filter((action) => { return action !== 'unlink'; });
    }

    let button;
    if (allowedActions.length === 1) {
      button = (
        <button className="btn btn-default btn-sm"
                onClick={this.openModal.bind(this, allowedActions[0])}>
          {toTitleCase(allowedActions[0]) + ' ' + plugin.title}
        </button>
      );
    } else {
      button = (
        <div className="btn-group">
          <DropdownLink
            caret={false}
            className="btn btn-default btn-sm"
            title={<span>
                     {plugin.title}
                     <span className="icon-arrow-down" style={{marginLeft: 3, marginRight: -3}} />
                   </span>}>
            {allowedActions.map((action) => {
              return (
                <MenuItem key={action} noAnchor={true}>
                  <a onClick={this.openModal.bind(this, action)}>{toTitleCase(action)}</a>
                </MenuItem>
              );
            })}
          </DropdownLink>
        </div>
      );
    }

    return (
      <span>
        {button}
        <Modal show={this.state.showModal} onHide={this.closeModal}
               animation={false} backdrop="static">
          <Modal.Header closeButton>
            <Modal.Title>{plugin.title + ' Issue'}</Modal.Title>
          </Modal.Header>
          <Modal.Body>
            <IssuePlugin plugin={this.props.plugin}
                         actionType={this.state.actionType}
                         onSuccess={this.closeModal}/>
          </Modal.Body>
        </Modal>
      </span>
    );
  }
});

export default IssuePluginActions;
